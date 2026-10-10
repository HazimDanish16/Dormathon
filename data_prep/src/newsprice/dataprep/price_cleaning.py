"""Deterministic PriceCatcher cleaning.

Observation key: (date, premise_code, item_code). Order of operations:
 1. Reject rows with an invalid date/key or a null, non-numeric, non-finite,
    zero or negative price (reason recorded).
 2. Drop exact duplicates (same key AND price), keeping the first.
 3. Reject every row of a key that appears with conflicting prices (we cannot
    know which is right and will not pick one).
 4. Flag outliers: price > ratio x or < 1/ratio x the item's median daily price
    over the PRECEDING `window_days` days (default 90, min 3 observed days: many items are surveyed only weekly) (current day excluded, so no future
    data is used). Needs `min_baseline_days` days of history, otherwise the
    row is kept and marked baseline_ok=False.
Flagged outliers stay in the observations file (outlier_flag=True) so they can
be audited; daily statistics exclude them. No interpolation or forward fill.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from .paths import DataPaths

KEY = ["date", "premise_code", "item_code"]
OBS_COLUMNS = [
    "date",
    "premise_code",
    "item_code",
    "price",
    "baseline_median",
    "baseline_ok",
    "outlier_flag",
    "source_month",
]
DAILY_COLUMNS = [
    "date",
    "item_code",
    "median_price",
    "p25_price",
    "p75_price",
    "n_premises",
    "n_obs",
    "n_outliers_flagged",
]


@dataclass
class CleanResult:
    observations: pd.DataFrame
    rejected: pd.DataFrame
    stats: dict


def read_item_observations(paths: DataPaths) -> pd.DataFrame:
    files = sorted(paths.raw_price_items.glob("pricecatcher_items_*.parquet"))
    if not files:
        raise FileNotFoundError(f"No monthly item files in {paths.raw_price_items}. Run scripts/download_prices.py first.")
    frames = []
    for f in files:
        df = pd.read_parquet(f)
        df["source_month"] = f.stem.rsplit("_", 1)[1]
        frames.append(df)
    return pd.concat(frames, ignore_index=True)


def causal_baseline(daily: pd.DataFrame, window_days: int = 90, min_baseline_days: int = 3) -> pd.DataFrame:
    """Per (item, date): median of daily item medians over the previous
    `window_days` days, excluding the date itself. Input: item_code, date, daily_median."""
    parts = []
    for item, g in daily.groupby("item_code", sort=True):
        s = g.set_index("date")["daily_median"].sort_index()
        b = s.rolling(f"{window_days}D", closed="left", min_periods=min_baseline_days).median()
        parts.append(pd.DataFrame({"item_code": item, "date": b.index, "baseline_median": b.to_numpy()}))
    return pd.concat(parts, ignore_index=True) if parts else pd.DataFrame(columns=["item_code", "date", "baseline_median"])


def clean_observations(
    obs: pd.DataFrame,
    *,
    window_days: int = 90,
    min_baseline_days: int = 3,
    ratio: float = 3.0,
) -> CleanResult:
    df = obs.copy()
    stats: dict = {"rows_input": int(len(df)), "ratio": ratio, "window_days": window_days, "min_baseline_days": min_baseline_days}
    if "source_month" not in df.columns:
        df["source_month"] = ""

    raw_price = df["price"]
    df["date"] = pd.to_datetime(df["date"], errors="coerce").dt.normalize()
    df["price"] = pd.to_numeric(df["price"], errors="coerce")
    df["item_code"] = pd.to_numeric(df["item_code"], errors="coerce")
    df["premise_code"] = pd.to_numeric(df["premise_code"], errors="coerce")

    reason = pd.Series("", index=df.index, dtype="object")

    def mark(mask: pd.Series, name: str) -> None:
        reason.loc[mask & (reason == "")] = name

    mark(df["date"].isna(), "invalid_date")
    mark(df["item_code"].isna() | df["premise_code"].isna(), "missing_key")
    mark(raw_price.isna(), "null_price")
    mark(df["price"].isna() & raw_price.notna(), "non_numeric_price")
    mark(pd.Series(np.isinf(df["price"].to_numpy(dtype="float64", na_value=np.nan)), index=df.index), "non_finite_price")
    mark(df["price"] <= 0, "non_positive_price")

    valid = df[reason == ""].copy()
    rejected = df[reason != ""].assign(reject_reason=reason[reason != ""])
    valid["item_code"] = valid["item_code"].astype("int64")
    valid["premise_code"] = valid["premise_code"].astype("int64")
    valid["price"] = valid["price"].astype("float64")

    dup = valid.duplicated(subset=KEY + ["price"], keep="first")
    stats["exact_duplicates_dropped"] = int(dup.sum())
    rejected = pd.concat([rejected, valid[dup].assign(reject_reason="exact_duplicate")], ignore_index=True)
    valid = valid[~dup]

    conflict = valid.groupby(KEY)["price"].transform("nunique") > 1
    stats["key_conflict_rows_rejected"] = int(conflict.sum())
    stats["key_conflict_keys"] = int(valid[conflict].groupby(KEY).ngroups) if conflict.any() else 0
    rejected = pd.concat([rejected, valid[conflict].assign(reject_reason="key_conflict")], ignore_index=True)
    valid = valid[~conflict].copy()

    daily = valid.groupby(["item_code", "date"], as_index=False)["price"].median().rename(columns={"price": "daily_median"})
    baseline = causal_baseline(daily, window_days, min_baseline_days)
    valid = valid.merge(baseline, on=["item_code", "date"], how="left")
    valid["baseline_ok"] = valid["baseline_median"].notna()
    valid["outlier_flag"] = valid["baseline_ok"] & (
        (valid["price"] > ratio * valid["baseline_median"]) | (valid["price"] < valid["baseline_median"] / ratio)
    )

    stats["rows_rejected_total"] = int(len(rejected))
    stats["rejected_by_reason"] = {k: int(v) for k, v in rejected["reject_reason"].value_counts().items()}
    stats["rows_after_cleaning"] = int(len(valid))
    stats["outliers_flagged"] = int(valid["outlier_flag"].sum())
    stats["rows_without_baseline"] = int((~valid["baseline_ok"]).sum())
    stats["rows_valid_for_stats"] = int((~valid["outlier_flag"]).sum())
    stats["missing_values_input"] = {c: int(obs[c].isna().sum()) for c in obs.columns if c != "source_month"}

    out = valid[OBS_COLUMNS].sort_values(["item_code", "date", "premise_code"], ignore_index=True)
    rej_cols = [c for c in ["date", "premise_code", "item_code", "price", "source_month", "reject_reason"] if c in rejected.columns]
    rejected = rejected[rej_cols].copy()
    # Keep raw values for audit: invalid values may not be numeric.
    for c in ("date", "premise_code", "item_code", "price"):
        if c in rejected.columns:
            rejected[c] = rejected[c].astype("string")
    return CleanResult(out, rejected.reset_index(drop=True), stats)


def daily_item_stats(observations: pd.DataFrame) -> pd.DataFrame:
    """Per item and date statistics from non-outlier observations."""
    valid = observations[~observations["outlier_flag"]]
    g = valid.groupby(["date", "item_code"])
    daily = g["price"].agg(median_price="median", p25_price=lambda s: s.quantile(0.25), p75_price=lambda s: s.quantile(0.75), n_obs="size").reset_index()
    daily["n_premises"] = g["premise_code"].nunique().to_numpy()
    flagged = observations[observations["outlier_flag"]].groupby(["date", "item_code"]).size().rename("n_outliers_flagged").reset_index()
    daily = daily.merge(flagged, on=["date", "item_code"], how="left")
    daily["n_outliers_flagged"] = daily["n_outliers_flagged"].fillna(0).astype("int64")
    daily["n_obs"] = daily["n_obs"].astype("int64")
    daily["n_premises"] = daily["n_premises"].astype("int64")
    return daily[DAILY_COLUMNS].sort_values(["item_code", "date"], ignore_index=True)


def write_outputs(paths: DataPaths, result: CleanResult, daily: pd.DataFrame) -> None:
    import json

    paths.ensure()
    paths.processed.mkdir(parents=True, exist_ok=True)
    paths.reports.mkdir(parents=True, exist_ok=True)
    result.observations.to_parquet(paths.price_observations, index=False)
    daily.to_parquet(paths.daily_item_prices, index=False)
    result.rejected.to_parquet(paths.rejected_prices, index=False)
    stats = {**result.stats, "daily_rows": int(len(daily)), "first_date": str(daily["date"].min().date()), "last_date": str(daily["date"].max().date())}
    (paths.stats / "clean_prices.json").write_text(json.dumps(stats, indent=2))
