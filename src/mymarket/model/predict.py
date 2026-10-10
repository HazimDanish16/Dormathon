"""CPU inference through the exported pipeline; no training."""

import numpy as np
import pandas as pd

from mymarket.config import Settings
from mymarket.errors import AppError
from mymarket.model.artifacts import ArtifactBundle
from mymarket.model.features import EVENT_WORDS
from mymarket.filter.aliases import contains


class Predictor:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.bundle = ArtifactBundle(settings)

    def metadata(self):
        if self.settings.data_mode == "fixture":
            return {"model_version": "FAKE-test-double-v1", "horizon_days": 14,
                    "min_confidence": .55, "thresholds": {"rice": .01, "egg": .01, "cooking_oil": .01, "chicken": .01}}
        bundle = self.bundle.load()
        return {"model_version": bundle.manifest.model_version, "horizon_days": bundle.thresholds.horizon_days,
                "min_confidence": bundle.thresholds.min_confidence, "thresholds": bundle.thresholds.products}

    def predict(self, text: str, products: list[tuple[str, str]], min_confidence=None):
        metadata = self.metadata()
        threshold = metadata["min_confidence"] if min_confidence is None else min_confidence
        if not 0 <= threshold <= 1:
            raise AppError("Invalid confidence threshold.", "min_confidence must be 0..1.")
        if not products:
            return []
        if self.settings.data_mode == "fixture":
            # Fixed test-double probabilities, never trained or reported as model accuracy.
            classes, probabilities = ["DOWN", "STABLE", "UP"], np.tile([.1, .1, .8], (len(products), 1))
        else:
            frame = pd.DataFrame([{"text": text, "product": product, "domain": domain} for product, domain in products])
            try:
                probabilities = np.asarray(self.bundle.model.predict_proba(frame), dtype=float)
            except Exception as exc:
                raise AppError("Model inference failed.", "Validate the export with scripts/validate_handoff.py; preprocessing must run on CPU.") from exc
            classes = self.bundle.classes
        if probabilities.shape != (len(products), 3) or not np.isfinite(probabilities).all() or (probabilities < 0).any() or (probabilities > 1).any() or not np.allclose(probabilities.sum(axis=1), 1, atol=1e-5):
            raise AppError("Invalid model probabilities.", "predict_proba must return finite normalized probabilities for all three classes.")
        output = []
        for (product, domain), row in zip(products, probabilities):
            probs = dict(zip(classes, map(float, row)))
            direction = max(probs, key=probs.get)
            output.append({"product": product, "domain": domain, "direction": direction, "probs": probs,
                           "confidence": probs[direction], "abstained": probs[direction] < threshold,
                           "triggers": [word for word in EVENT_WORDS if contains(text, word)], **metadata})
        return output
