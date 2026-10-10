"""Download the pinned embedding weights and smoke-test CPU inference."""

import logging
import sys

from mymarket.config import Settings
from mymarket.filter.embed_filter import MODEL

if __name__ == "__main__":
    logging.basicConfig(stream=sys.stderr, level=logging.INFO)
    from sentence_transformers import SentenceTransformer
    settings = Settings.from_env()
    model = SentenceTransformer(MODEL, revision=settings.embedding_revision, device="cpu")
    vector = model.encode(["query: Malaysian chicken supply and prices"], normalize_embeddings=True, show_progress_bar=False)
    print(f"Pinned CPU embedding model ready: {vector.shape}")
