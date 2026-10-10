"""CPU embeddings with persistent cache, and an explicit fixture test double."""

import hashlib
import json
import logging
import threading

import numpy as np

from mymarket.config import Settings
from mymarket.errors import AppError
from mymarket.store.db import ArticleStore

MODEL = "intfloat/multilingual-e5-small"
logger = logging.getLogger(__name__)


class Embedder:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.model = None
        self.lock = threading.RLock()
        self.key = "FAKE-embedder-v1" if settings.data_mode == "fixture" else MODEL + "@" + settings.embedding_revision

    def encode(self, texts: list[str]) -> np.ndarray:
        if self.settings.data_mode == "fixture":
            # Deliberate test double: no semantic accuracy claim.
            return np.tile(np.array([1.0, 0.0], dtype=np.float32), (len(texts), 1))
        with self.lock:
            store = ArticleStore(self.settings.sqlite_path)
            hashes = [hashlib.sha256(text.encode()).hexdigest() for text in texts]
            with store.connection() as db:
                cached = [db.execute("SELECT vector FROM embeddings WHERE model_key=? AND text_hash=?", (self.key, key)).fetchone() for key in hashes]
            missing = [i for i, value in enumerate(cached) if value is None]
            if missing:
                try:
                    if self.model is None:
                        from sentence_transformers import SentenceTransformer
                        self.model = SentenceTransformer(MODEL, revision=self.settings.embedding_revision, device="cpu", local_files_only=True)
                    vectors = self.model.encode([texts[i] for i in missing], normalize_embeddings=True, show_progress_bar=False, device="cpu")
                except Exception as exc:
                    raise AppError("CPU embedding model unavailable.", "Run scripts/cache_embeddings.py once with network access; no alias-only fallback is used.") from exc
                with store.connection() as db:
                    for index, vector in zip(missing, vectors):
                        encoded = json.dumps(vector.tolist())
                        db.execute("INSERT OR REPLACE INTO embeddings VALUES (?, ?, ?)", (self.key, hashes[index], encoded))
                        cached[index] = {"vector": encoded}
            return np.asarray([json.loads(row["vector"]) for row in cached], dtype=np.float32)


def filter_threshold(settings: Settings) -> tuple[float, bool]:
    path = settings.config_dir / "filter_threshold.json"
    if not path.is_file():
        logger.warning("Relevance threshold 0.80 is untuned")
        return 0.80, False
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        threshold = float(data["threshold"])
        if not 0 <= threshold <= 1:
            raise ValueError("range")
        return threshold, data.get("audited") is True
    except Exception as exc:
        raise AppError("Invalid relevance threshold.", "filter_threshold.json requires threshold in [0,1] and audited boolean.") from exc
