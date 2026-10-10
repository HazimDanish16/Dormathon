"""Version 1 handoff validation. No training or historical preprocessing."""

import numpy as np
import pandas as pd

from mymarket.config import Settings, load_products
from mymarket.errors import AppError
from mymarket.store.db import canonical_url

SCHEMAS = {
    "news_clean.parquet": ["article_id", "title", "summary", "body", "source", "url", "language", "published_at"],
    "price_index.parquet": ["product", "date", "index", "n_premises"],
    "item_mapping.csv": ["product", "item_code"],
    "examples.parquet": ["article_id", "product", "domain", "published_at", "text", "realized_return", "momentum_return"],
}


def read_data(settings: Settings, name: str) -> pd.DataFrame:
    path = settings.data_file(name)
    if not path.is_file():
        raise AppError(f"Missing data input: {name}.", "Obtain the teammate handoff described in DATA_AGENT_PROMPT.md; fixtures require explicit fixture mode.")
    try:
        frame = pd.read_csv(path) if name.endswith(".csv") else pd.read_parquet(path)
        return validate_frame(frame, name, settings)
    except AppError:
        raise
    except Exception as exc:
        raise AppError(f"Invalid data input: {name}.", "Check its schema against DATA_AGENT_PROMPT.md.") from exc


def validate_frame(frame: pd.DataFrame, name: str, settings: Settings) -> pd.DataFrame:
    frame = frame.copy()
    required = SCHEMAS[name]
    if frame.empty or set(required) - set(frame.columns) or frame[required].isna().any().any():
        raise AppError(f"Invalid or empty {name}.", "Required columns must exist and contain no nulls: " + ", ".join(required))
    if settings.data_mode == "real" and "synthetic" in frame and frame["synthetic"].ne(False).any():
        raise AppError("Synthetic data cannot run in real mode.", "Use MYMARKET_DATA_MODE=fixture for fake inputs.")
    if settings.data_mode == "fixture" and ("synthetic" not in frame or not frame["synthetic"].eq(True).all()):
        raise AppError("Fixture data must be marked synthetic.", "Generate FAKE fixtures using scripts/generate_fixtures.py.")
    domains = load_products(settings).domains
    products = {product for domain in domains.values() for product in domain.products}
    for column in set(required) - {"item_code", "index", "n_premises", "realized_return", "momentum_return", "published_at", "date"}:
        if not frame[column].map(lambda value: isinstance(value, str)).all():
            raise ValueError(f"{column} must contain strings")
    if "product" in frame and not set(frame["product"]).issubset(products):
        raise ValueError("Unknown products")
    if "domain" in frame and any(row.product not in domains.get(row.domain, type("Empty", (), {"products": {}})()).products for row in frame.itertuples()):
        raise ValueError("Product/domain mismatch")
    if "published_at" in frame:
        if not frame["published_at"].map(lambda value: pd.Timestamp(value).tzinfo is not None).all():
            raise ValueError("published_at must be timezone-aware")
        frame["published_at"] = pd.to_datetime(frame["published_at"], utc=True)
    if "date" in frame:
        dates = pd.to_datetime(frame["date"], errors="raise")
        if dates.dt.tz is not None or not dates.eq(dates.dt.normalize()).all():
            raise ValueError("date must be a timezone-free calendar date")
        frame["date"] = dates.dt.date
    for column in {"index", "realized_return", "momentum_return", "item_code", "n_premises"} & set(required):
        if not pd.api.types.is_numeric_dtype(frame[column]) or not np.isfinite(frame[column]).all():
            raise ValueError(f"{column} must contain finite numbers")
    if "index" in frame and (frame["index"] <= 0).any():
        raise ValueError("index must be positive")
    for column in {"item_code", "n_premises"} & set(required):
        if (frame[column] < (1 if column == "n_premises" else 0)).any() or (frame[column] % 1 != 0).any():
            raise ValueError(f"{column} must contain nonnegative integers (premise counts positive)")
    keys = {"news_clean.parquet": ["article_id"], "price_index.parquet": ["product", "date"],
            "item_mapping.csv": ["product", "item_code"], "examples.parquet": ["article_id", "product"]}[name]
    if frame.duplicated(keys).any():
        raise ValueError("Duplicate rows: " + ", ".join(keys))
    if "url" in frame:
        normalized = frame.url.map(canonical_url)
        if normalized.duplicated().any():
            raise ValueError("Duplicate article URLs")
    return frame
