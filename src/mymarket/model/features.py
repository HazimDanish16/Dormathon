"""Importable preprocessing transformers for the teammate's fitted Colab pipeline."""

import numpy as np
from sklearn.base import BaseEstimator, TransformerMixin

from mymarket.filter.aliases import contains

EVENT_WORDS = ["subsidy", "subsidi", "ceiling price", "harga siling", "shortage", "kekurangan",
               "flood", "banjir", "import ban", "export ban", "tariff", "levy", "sst", "price control",
               "kawalan harga", "hari raya", "ramadan", "chinese new year", "ringgit", "drought",
               "bird flu", "feed cost", "minimum wage"]


class EventFlags(BaseEstimator, TransformerMixin):
    def fit(self, X, y=None):
        return self

    def transform(self, X):
        texts = X.iloc[:, 0] if getattr(X, "ndim", 1) == 2 else X
        return np.asarray([[float(contains(str(text), word)) for word in EVENT_WORDS] for text in texts])


class E5Features(BaseEstimator, TransformerMixin):
    def __init__(self, revision="614241f622f53c4eeff9890bdc4f31cfecc418b3", model_name="intfloat/multilingual-e5-small"):
        self.revision = revision
        self.model_name = model_name

    def fit(self, X, y=None):
        return self

    def transform(self, X):
        from sentence_transformers import SentenceTransformer
        if not hasattr(self, "_model"):
            from huggingface_hub import snapshot_download
            folder = snapshot_download(self.model_name, revision=self.revision, local_files_only=True)
            self._model = SentenceTransformer(folder, device="cpu", local_files_only=True)
        texts = X.iloc[:, 0] if getattr(X, "ndim", 1) == 2 else X
        return self._model.encode(["query: " + str(text) for text in texts], normalize_embeddings=True, show_progress_bar=False, device="cpu")

    def __getstate__(self):
        # Colab exports never retain GPU tensors or a live encoder instance.
        return {key: value for key, value in self.__dict__.items() if key != "_model"}
