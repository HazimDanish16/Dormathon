"""Validate probabilities, export compatibility, and exact-date price context."""

import hashlib
import importlib.metadata
import json
from dataclasses import replace
from pathlib import Path

import joblib
import numpy as np
import pytest

from mymarket.config import Settings
from mymarket.contracts import read_data
from mymarket.errors import AppError
from mymarket.model.artifacts import ArtifactBundle, CLASSES, FILES
from mymarket.model.predict import Predictor
from mymarket.service import MarketService
from mymarket.fixtures import generate

ROOT = Path(__file__).resolve().parents[1]


class ExportedTestDouble:
    classes_ = ["STABLE", "UP", "DOWN"]
    def predict_proba(self, frame):
        assert list(frame.columns) == ["text", "product", "domain"]
        return np.tile([.1, .7, .2], (len(frame), 1))


def export_bundle(destination):
    destination.mkdir()
    joblib.dump(ExportedTestDouble(), destination / "model.joblib")
    per_class = {label: {"precision": .5, "recall": .5, "f1": .5, "support": 2} for label in CLASSES}
    # Controlled metadata exclusively for validator tests, never a served real export.
    metrics = {"schema_version": 1, "model_version": "test", "synthetic": False,
               "class_order": ExportedTestDouble.classes_,
               "dataset_provenance": {"purpose": "unit test only"},
               "test": {"macro_f1": .5, "macro_f1_ci95": [.4, .6], "per_class": per_class,
                        "confusion_matrix": [[1, 1, 0], [0, 1, 1], [1, 0, 1]], "directional_accuracy": None, "alert_precision": None},
               "baselines": {name: {"macro_f1": .3} for name in ["majority", "momentum", "keyword"]}, "rolling_origin": [], "limitations": ["Test double"]}
    values = {"label_map.json": {"classes": ExportedTestDouble.classes_},
              "thresholds.json": {"horizon_days": 14, "min_confidence": .8, "products": dict.fromkeys(["rice", "egg", "cooking_oil", "chicken"], .01)},
              "metrics.json": metrics}
    for name, data in values.items():
        (destination / name).write_text(json.dumps(data), encoding="utf-8")
    manifest = {"schema_version": 1, "model_version": "test", "synthetic": False,
                "features": ["text", "product", "domain"], "body_chars": 1500,
                "embedding_model": "intfloat/multilingual-e5-small", "embedding_revision": Settings.embedding_revision,
                "packages": {name: importlib.metadata.version(name) for name in ["numpy", "pandas", "scikit-learn", "joblib"]},
                "files": {name: hashlib.sha256((destination / name).read_bytes()).hexdigest() for name in FILES}}
    (destination / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    return Settings(ROOT, ROOT / "config", model_dir=destination)


def test_export_class_order_and_abstention(tmp_path):
    settings = export_bundle(tmp_path / "models")
    prediction = Predictor(settings).predict("Chicken shortage", [("chicken", "staple_food")])[0]
    assert prediction["direction"] == "UP"
    assert prediction["probs"] == {"STABLE": .1, "UP": .7, "DOWN": .2}
    assert prediction["abstained"] is True
    assert prediction["triggers"] == ["shortage"]


@pytest.mark.parametrize("failure", ["checksum", "synthetic", "package", "revision"])
def test_reject_bad_export(tmp_path, failure):
    settings = export_bundle(tmp_path / "models")
    path = settings.artifacts_path / "manifest.json"
    manifest = json.loads(path.read_text())
    if failure == "checksum":
        (settings.artifacts_path / "model.joblib").write_bytes(b"corrupt")
    elif failure == "synthetic":
        manifest["synthetic"] = True
    elif failure == "package":
        manifest["packages"]["scikit-learn"] = "0.0.0"
    else:
        manifest["embedding_revision"] = "a" * 40
    path.write_text(json.dumps(manifest))
    with pytest.raises(AppError):
        ArtifactBundle(settings).load()


def test_invalid_probabilities_fail_closed(tmp_path):
    settings = export_bundle(tmp_path / "models")
    predictor = Predictor(settings)
    predictor.bundle.load().model.predict_proba = lambda frame: np.array([[float("nan"), .1, .9]])
    with pytest.raises(AppError, match="probabilities"):
        predictor.predict("text", [("chicken", "staple_food")])


def test_exact_price_gaps_and_fixture_provenance(tmp_path):
    generate(tmp_path)
    settings = Settings(ROOT, ROOT / "config", data_mode="fixture", data_dir=tmp_path,
                        database_path=tmp_path / "FAKE.sqlite3")
    service = MarketService(settings)
    result = service.price_context("chicken", days=30)
    assert result["synthetic"]
    assert len(result["series_tail"]) == 30
    frame = read_data(settings, "price_index.parquet")
    from datetime import date, timedelta
    comparison = date.fromisoformat(result["data_as_of"]) - timedelta(days=7)
    frame = frame[~((frame["product"] == "chicken") & (frame["date"] == comparison))]
    frame.to_parquet(settings.data_file("price_index.parquet"), index=False)
    assert service.price_context("chicken")["change_7d_pct"] is None
    assert service.backtest_report()["metrics"] is None
    with pytest.raises(AppError):
        service.predict_impact(text="hello", products=["missing"])
    with pytest.raises(AppError):
        service.predict_impact(text="hello", url="https://example.com")
