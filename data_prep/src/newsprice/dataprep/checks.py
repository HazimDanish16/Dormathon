"""Automated dataset checks (used by scripts/validate_datasets.py and the tests).

Every function takes plain DataFrames and returns a list of Check results so
the same code validates both the real outputs and synthetic test fixtures.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from .mapping import APPROVED_COLUMNS, PRODUCT_IDS
from .news_cleaning import ADDED_COLUMNS, PRD_COLUMNS
from .price_cleaning import DAILY_COLUMNS, KEY, OBS_COLUMNS
from .price_index import INDEX_COLUMNS

ALLOWED_FLAGS = {"ok", "reference_period", "no_eligible_items", "low_items", "composition_change", "gap_after_missing_days"}


@dataclass
class Check:
    name: str
    passed: bool
    detail: str = ""


def _c(name: str, passed: bool, detail: str = "") -> Check:
    return Check(name, bool(passed), detail if not passed else (detail or "ok"))


def _has_columns(df: pd.DataFrame, expected: list[str], label: str) -> Check:
    missing = [c for c in expected if c not in df.columns]
    return _c(f"{label}: schema columns present", not missing, f"missing {missing}")


def check_mapping(approved: pd.DataFrame, lookup: pd.DataFrame | None = None) -> list[Check]:
    out = [_has_columns(approved, APPROVED_COLUMNS, "item_mapping")]
    if out[0].passed:
        out.append(_c("item_mapping: every include is yes/no (no unresolved review)", approved["include"].isin(["yes", "no"]).all()))
        out.append(_c("item_mapping: item_code unique", approved["item_code"].is_unique))
        for p in PRODUCT_IDS:
            n = int(((approved["proposed_product"] == p) & (approved["include"] == "yes")).sum())
            out.append(_c(f"item_mapping: {p} has at least one approved item", n > 0, f"{n} approved"))
        if lookup is not None:
            unknown = sorted(set(approved["item_code"]) - set(lookup["item_code"]))
            out.append(_c("item_mapping: all item codes exist in lookup_item", not unknown, f"unknown {unknown[:10]}"))
    return out


def check_observations(obs: pd.DataFrame, approved: pd.DataFrame | None = None) -> list[Check]:
    out = [_has_columns(obs, OBS_COLUMNS, "price_observations")]
    if not out[0].passed:
        return out
    out.append(_c("price_observations: dates valid (no nulls)", obs["date"].notna().all()))
    out.append(_c("price_observations: prices finite and > 0", np.isfinite(obs["price"]).all() and (obs["price"] > 0).all()))
    dup = int(obs.duplicated(subset=KEY).sum())
    out.append(_c("price_observations: no duplicate (date, premise, item) keys", dup == 0, f"{dup} duplicates"))
    out.append(_c("price_observations: outlier_flag is boolean", obs["outlier_flag"].dtype == bool))
    out.append(_c("price_observations: outliers only judged where a baseline exists", not (obs["outlier_flag"] & ~obs["baseline_ok"]).any()))
    out.append(_c("price_observations: dates span a sensible range", obs["date"].min() > pd.Timestamp("2015-01-01") and obs["date"].max() < pd.Timestamp.now() + pd.Timedelta(days=2)))
    if approved is not None:
        extra = sorted(set(obs["item_code"]) - set(approved["item_code"]))
        out.append(_c("price_observations: item codes all exist in the approved mapping", not extra, f"not in mapping: {extra[:10]}"))
    return out


def check_daily(daily: pd.DataFrame) -> list[Check]:
    out = [_has_columns(daily, DAILY_COLUMNS, "daily_item_prices")]
    if not out[0].passed:
        return out
    out.append(_c("daily_item_prices: (item, date) unique", not daily.duplicated(subset=["item_code", "date"]).any()))
    out.append(_c("daily_item_prices: sorted by item then date", daily.sort_values(["item_code", "date"]).reset_index(drop=True)[["item_code", "date"]].equals(daily.reset_index(drop=True)[["item_code", "date"]])))
    out.append(_c("daily_item_prices: prices positive", (daily["median_price"] > 0).all()))
    out.append(_c("daily_item_prices: p25 <= median <= p75", ((daily["p25_price"] <= daily["median_price"] + 1e-9) & (daily["median_price"] <= daily["p75_price"] + 1e-9)).all()))
    out.append(_c("daily_item_prices: 1 <= n_premises <= n_obs", ((daily["n_premises"] >= 1) & (daily["n_premises"] <= daily["n_obs"])).all()))
    return out


def trailing_smooth(raw_by_date: pd.Series, days: int = 7, min_periods: int = 3) -> pd.Series:
    return raw_by_date.dropna().rolling(f"{days}D", min_periods=min_periods).mean()


def check_index(index: pd.DataFrame, approved: pd.DataFrame | None = None, ref_end: pd.Timestamp | None = None) -> list[Check]:
    out = [_has_columns(index, INDEX_COLUMNS, "price_index")]
    if not out[0].passed:
        return out
    for col in ("price_index_raw", "price_index_smoothed", "price_index_chained"):
        vals = index[col].dropna()
        out.append(_c(f"price_index: {col} finite and positive", np.isfinite(vals).all() and (vals > 0).all()))
    out.append(_c("price_index: (product, date) unique", not index.duplicated(subset=["product", "date"]).any()))
    out.append(_c("price_index: dates ordered within each product", all(g["date"].is_monotonic_increasing for _, g in index.groupby("product"))))
    bad_flags = sorted({f for v in index["data_quality_flag"] for f in str(v).split(";")} - ALLOWED_FLAGS)
    out.append(_c("price_index: data_quality_flag values valid", not bad_flags, f"unexpected {bad_flags}"))
    out.append(_c("price_index: all four products present", set(PRODUCT_IDS) <= set(index["product"]), f"found {sorted(set(index['product']))}"))
    # No look-ahead: smoothed must equal a trailing window recomputed from the raw series.
    ok = True
    for _, g in index.groupby("product"):
        expect = trailing_smooth(g.loc[~g["data_quality_flag"].str.contains("low_items")].set_index("date")["price_index_raw"])
        got = g.set_index("date")["price_index_smoothed"].dropna()
        ok &= bool(np.allclose(expect.reindex(got.index).to_numpy(), got.to_numpy(), equal_nan=True))
    out.append(_c("price_index: smoothing is trailing (no look-ahead)", ok))
    if ref_end is not None:
        early = index[index["date"] <= ref_end]
        flagged = early["data_quality_flag"].str.contains("reference_period").all() if len(early) else True
        out.append(_c("price_index: dates inside the normalisation window are flagged reference_period", flagged))
    cov = index.groupby("product")["date"].agg(["min", "max", "count"])
    out.append(_c("price_index: source coverage documented per product", (cov["count"] > 0).all(), cov.to_string()))
    return out


def check_news(news: pd.DataFrame, min_text_chars: int = 100, all_columns: list[str] | None = None) -> list[Check]:
    """`all_columns` lets callers validate the schema of the full file while
    passing only the columns the other checks need (the text fields are large)."""
    cols = pd.DataFrame(columns=all_columns) if all_columns is not None else news
    out = [_has_columns(cols, PRD_COLUMNS + ADDED_COLUMNS, "historical_news")]
    if not out[0].passed:
        return out
    tz = getattr(news["published_at"].dt, "tz", None)
    out.append(_c("historical_news: published_at is timezone-aware Asia/Kuala_Lumpur", tz is not None and str(tz) == "Asia/Kuala_Lumpur", f"tz={tz}"))
    out.append(_c("historical_news: no missing publication dates", news["published_at"].notna().all()))
    out.append(_c("historical_news: published_date_local matches published_at", (pd.to_datetime(news["published_date_local"]).to_numpy() == news["published_at"].dt.tz_localize(None).dt.normalize().to_numpy()).all()))
    out.append(_c(f"historical_news: text_clean at least {min_text_chars} chars", (news["text_clean"].str.len() >= min_text_chars).all()))
    nn = news.loc[news["url_normalized"] != "", "url_normalized"]
    out.append(_c("historical_news: normalised URLs unique", nn.is_unique, f"{int(nn.duplicated().sum())} duplicates"))
    out.append(_c("historical_news: content_id unique", news.loc[news["content_id"] != "", "content_id"].is_unique))
    out.append(_c("historical_news: no unsanitised HTML tags in text_clean", not news["text_clean"].str.contains(r"<[a-zA-Z/][^>]*>", regex=True).any()))
    return out


def summarize(checks: list[Check]) -> tuple[int, int]:
    return sum(c.passed for c in checks), len(checks)
