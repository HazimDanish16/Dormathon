"""Validate trusted Colab exports before deserializing the prediction pipeline."""

import hashlib
import importlib.metadata
import json
import re
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, model_validator

from mymarket.config import Settings, load_products
from mymarket.errors import AppError

CLASSES = {"UP", "DOWN", "STABLE"}
FILES = ["model.joblib", "label_map.json", "thresholds.json", "metrics.json"]


class Manifest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: int = Field(ge=1, le=1)
    model_version: str = Field(min_length=1)
    synthetic: bool
    features: list[str]
    body_chars: int = Field(ge=1500, le=1500)
    embedding_model: str
    embedding_revision: str = Field(pattern=r"^[0-9a-f]{40}$")
    packages: dict[str, str] = Field(min_length=4)
    files: dict[str, str]

    @model_validator(mode="after")
    def check(self):
        if self.features != ["text", "product", "domain"] or self.embedding_model != "intfloat/multilingual-e5-small":
            raise ValueError("Unsupported feature interface")
        if set(self.files) != set(FILES) or not all(re.fullmatch(r"[0-9a-f]{64}", value) for value in self.files.values()):
            raise ValueError("Export hashes must cover exactly the four artifacts")
        if not {"numpy", "pandas", "scikit-learn", "joblib"}.issubset(self.packages):
            raise ValueError("Missing serialization-critical package versions")
        return self


class Thresholds(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    horizon_days: int = Field(ge=14, le=14)
    min_confidence: float = Field(ge=0, le=1)
    products: dict[str, float] = Field(min_length=1)

    @model_validator(mode="after")
    def positive(self):
        if any(value < 0 for value in self.products.values()):
            raise ValueError("Label thresholds cannot be negative")
        return self


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def validate_metrics(data: dict, version: str) -> dict:
    if data.get("schema_version") != 1 or data.get("model_version") != version or data.get("synthetic") is not False:
        raise ValueError("Metrics provenance/version mismatch")
    if not isinstance(data.get("dataset_provenance"), dict) or not data["dataset_provenance"]:
        raise ValueError("Missing dataset provenance")
    test = data["test"]
    for key in ["macro_f1", "directional_accuracy", "alert_precision"]:
        value = test[key]
        if value is None and key != "macro_f1":
            continue
        if not isinstance(value, (int, float)) or not 0 <= value <= 1:
            raise ValueError("Invalid metric: " + key)
    ci = test["macro_f1_ci95"]
    if len(ci) != 2 or not 0 <= ci[0] <= test["macro_f1"] <= ci[1] <= 1:
        raise ValueError("Invalid confidence interval")
    if set(test["per_class"]) != CLASSES:
        raise ValueError("Missing per-class metrics")
    for result in test["per_class"].values():
        if any(not 0 <= result[key] <= 1 for key in ["precision", "recall", "f1"]) or result["support"] < 0:
            raise ValueError("Invalid class metrics")
    matrix = test["confusion_matrix"]
    if len(matrix) != 3 or any(len(row) != 3 or any(not isinstance(n, int) or n < 0 for n in row) for row in matrix):
        raise ValueError("Invalid confusion matrix")
    if not {"majority", "momentum", "keyword"}.issubset(data["baselines"]):
        raise ValueError("Missing required baselines")
    if not isinstance(data.get("rolling_origin"), list) or not isinstance(data.get("limitations"), list):
        raise ValueError("Missing rolling-origin results or limitations")
    return data


class ArtifactBundle:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.signature = None
        self.model = None

    def load(self):
        paths = [self.settings.artifacts_path / name for name in ["manifest.json", *FILES]]
        if not all(path.is_file() for path in paths):
            raise AppError("Colab model export is incomplete.", "Obtain all five files documented in DATA_AGENT_PROMPT.md from your teammate.")
        signature = tuple((path.stat().st_mtime_ns, path.stat().st_size) for path in paths)
        if signature == self.signature:
            return self
        try:
            manifest = Manifest.model_validate(read_json(paths[0]))
            if manifest.synthetic or self.settings.data_mode != "real":
                raise ValueError("Real artifacts cannot be substituted by synthetic artifacts")
            if manifest.embedding_revision != self.settings.embedding_revision:
                raise ValueError("Embedding revision differs from server configuration")
            for name, expected in manifest.packages.items():
                actual = importlib.metadata.version(name)
                if actual.split("+")[0] != expected.split("+")[0]:
                    raise ValueError(f"Package mismatch: {name}; exported {expected}, installed {actual}")
            for path in paths[1:]:
                if hashlib.sha256(path.read_bytes()).hexdigest() != manifest.files[path.name]:
                    raise ValueError("Artifact checksum mismatch: " + path.name)
            classes = read_json(paths[2])["classes"]
            if len(classes) != 3 or set(classes) != CLASSES:
                raise ValueError("All three class labels are required exactly once")
            thresholds = Thresholds.model_validate(read_json(paths[3]))
            configured = {product for domain in load_products(self.settings).domains.values() for product in domain.products}
            if not configured.issubset(thresholds.products):
                raise ValueError("Missing product thresholds")
            metrics = validate_metrics(read_json(paths[4]), manifest.model_version)
            import joblib
            model = joblib.load(paths[1])
            if not callable(getattr(model, "predict_proba", None)) or list(model.classes_) != classes:
                raise ValueError("Estimator classes differ from label_map.json")
        except Exception as exc:
            raise AppError("Colab model export failed validation.", str(exc) + "; check DATA_AGENT_PROMPT.md and re-export a compatible bundle.") from exc
        self.manifest, self.classes, self.thresholds, self.metrics, self.model = manifest, classes, thresholds, metrics, model
        self.signature = signature
        return self
