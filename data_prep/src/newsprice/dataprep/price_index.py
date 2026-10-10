"""Product price indexes from daily item prices (no labels, no forecasting).

Three series per product, all computed only from data observed up to each date:

price_index_raw       PRD method: each item is divided by its own reference median
                      (median of its daily medians over its first `per_item_days`
                      days, or over a FIXED window when per_item_days is None),
                      x100, then averaged over the items observed that day.
                      Items without enough reference data are excluded (never
                      treated as zero). An item only enters the index AFTER its own
                      reference window ends, so no baseline uses future data.
                      Dates before the first item is eligible are flagged
                      `reference_period`.
price_index_smoothed  Trailing 7-day mean of price_index_raw over observed dates with
                      at least min(3, eligible items) items (low_items days excluded) (window ends on the current date; nothing is filled in).
price_index_chained   Extra: chained index from day-to-day changes of each item
                      (gaps over `max_gap_days` ignored). Needs no baseline, so items
                      that appear later cannot make the index jump on entry.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

import numpy as np
import pandas as pd

from .mapping import PRODUCT_IDS

INDEX_COLUMNS = [
    "date",
    "product",
    "price_index_raw",
    "price_index_smoothed",
    "price_index_chained",
    "n_items",
    "n_items_chained",
    "n_premises",
    "data_quality_flag",
]
BASELINE_COLUMNS = ["product", "item_code", "baseline_median", "ref_days", "eligible", "ref_end", "baseline_available_date"]


@dataclass(frozen=True)
class IndexConfig:
    ref_start: pd.Timestamp
    ref_end: pd.Timestamp
    min_ref_days: int = 30
    smoothing_days: int = 7
    smoothing_min_periods: int = 3
    min_items: int = 3  # days with fewer observed items are flagged low_items and excluded from smoothing (capped at the product's eligible items)
    max_gap_days: int = 3
    per_item_days: int | None = 90  # None = fixed ref_start..ref_end window for all items

    @classmethod
    def from_strings(cls, ref_start: str, ref_end: str, **kw) -> "IndexConfig":
        return cls(pd.Timestamp(ref_start), pd.Timestamp(ref_end), **kw)


def compute_baselines(daily: pd.DataFrame, items: pd.DataFrame, cfg: IndexConfig) -> pd.DataFrame:
    """Reference median per included item. `items` has item_code, product.

    Per-item mode: window = item's first date .. first date + per_item_days - 1.
    Fixed mode: the shared ref_start..ref_end window."""
    d = daily[daily["item_code"].isin(items["item_code"])]
    if cfg.per_item_days is None:
        ref = d[(d["date"] >= cfg.ref_start) & (d["date"] <= cfg.ref_end)]
        agg = ref.groupby("item_code").agg(baseline_median=("median_price", "median"), ref_days=("date", "nunique")).reset_index()
        agg["ref_end"] = cfg.ref_end
    else:
        first = d.groupby("item_code")["date"].min().rename("first_date").reset_index()
        d = d.merge(first, on="item_code")
        ref = d[d["date"] < d["first_date"] + pd.Timedelta(days=cfg.per_item_days)]
        agg = ref.groupby("item_code").agg(baseline_median=("median_price", "median"), ref_days=("date", "nunique")).reset_index()
        agg = agg.merge(first, on="item_code")
        agg["ref_end"] = agg["first_date"] + pd.Timedelta(days=cfg.per_item_days - 1)
    out = items.merge(agg, on="item_code", how="left")
    out["ref_days"] = out["ref_days"].fillna(0).astype("int64")
    out["eligible"] = out["ref_days"] >= cfg.min_ref_days
    out["baseline_available_date"] = (out["ref_end"] + pd.Timedelta(days=1)).dt.date.astype("string")
    out["ref_end"] = out["ref_end"].dt.date.astype("string")
    return out[BASELINE_COLUMNS].sort_values(["product", "item_code"], ignore_index=True)


def chained_index(item_prices: pd.DataFrame, max_gap_days: int) -> pd.DataFrame:
    """Chained index (starts at 100) from item_code/date/median_price rows.
    Returns date, price_index_chained, n_items_chained."""
    df = item_prices.sort_values(["item_code", "date"]).copy()
    prev_price = df.groupby("item_code")["median_price"].shift(1)
    prev_date = df.groupby("item_code")["date"].shift(1)
    gap = (df["date"] - prev_date).dt.days
    # Mean of LOG returns: averaging simple returns of noisy prices drifts upward.
    df["ret"] = np.where((gap >= 1) & (gap <= max_gap_days), np.log(df["median_price"] / prev_price), np.nan)
    per_day = df.dropna(subset=["ret"]).groupby("date").agg(mean_ret=("ret", "mean"), n_items_chained=("item_code", "nunique"))
    dates = pd.Index(sorted(df["date"].unique()), name="date")
    frame = pd.DataFrame(index=dates).join(per_day)
    level = 100.0 * np.exp(frame["mean_ret"].fillna(0.0).cumsum())
    frame["price_index_chained"] = level.where(frame["mean_ret"].notna() | (frame.index == dates[0]))
    frame["n_items_chained"] = frame["n_items_chained"].fillna(0).astype("int64")
    return frame.reset_index()[["date", "price_index_chained", "n_items_chained"]]


def product_ref_end(baselines: pd.DataFrame, product: str, cfg: IndexConfig) -> pd.Timestamp:
    """Last date before the product has any point-in-time baseline."""
    if cfg.per_item_days is None:
        return cfg.ref_end
    el = baselines[(baselines["product"] == product) & baselines["eligible"]]
    return pd.to_datetime(el["ref_end"]).min() if len(el) else pd.Timestamp.max.normalize()


def _flags(frame: pd.DataFrame, ref_end: pd.Timestamp, min_items: int) -> pd.Series:
    flags = []
    prev_n = None
    prev_date = None
    for row in frame.itertuples(index=False):
        f = []
        if row.date <= ref_end:
            f.append("reference_period")
        if pd.isna(row.price_index_raw) or row.n_items == 0:
            f.append("no_eligible_items")
        elif row.n_items < min_items:
            f.append("low_items")
        if prev_n is not None and row.n_items != prev_n:
            f.append("composition_change")
        if prev_date is not None and (row.date - prev_date).days > 1:
            f.append("gap_after_missing_days")
        flags.append(";".join(f) if f else "ok")
        prev_n, prev_date = row.n_items, row.date
    return pd.Series(flags, index=frame.index)


def build_price_index(
    daily: pd.DataFrame,
    items: pd.DataFrame,
    premises_per_day: pd.DataFrame,
    cfg: IndexConfig,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Returns (index_frame, baselines).

    daily: daily_item_prices; items: item_code, product (approved, include=yes);
    premises_per_day: product, date, n_premises.
    """
    baselines = compute_baselines(daily, items, cfg)
    frames = []
    for product in [p for p in PRODUCT_IDS if p in set(items["product"])]:
        codes = items.loc[items["product"] == product, "item_code"]
        pdaily = daily[daily["item_code"].isin(codes)][["date", "item_code", "median_price"]]
        if pdaily.empty:
            continue
        eligible = baselines[(baselines["product"] == product) & baselines["eligible"]][["item_code", "baseline_median", "ref_end"]].copy()
        eligible["ref_end"] = pd.to_datetime(eligible["ref_end"])
        e = pdaily.merge(eligible, on="item_code")
        e = e[e["date"] > e["ref_end"]]  # point-in-time: baseline known only after the window
        e["ratio"] = 100.0 * e["median_price"] / e["baseline_median"]
        raw = e.groupby("date").agg(price_index_raw=("ratio", "mean"), n_items=("item_code", "nunique")).reset_index()
        chained = chained_index(pdaily, cfg.max_gap_days)
        frame = chained.merge(raw, on="date", how="outer").sort_values("date", ignore_index=True)
        frame["n_items"] = frame["n_items"].fillna(0).astype("int64")
        frame["n_items_chained"] = frame["n_items_chained"].fillna(0).astype("int64")
        required = max(1, min(cfg.min_items, int(len(eligible))))
        ok = frame["price_index_raw"].notna() & (frame["n_items"] >= required)
        s = frame.loc[ok].set_index("date")["price_index_raw"]
        smoothed = s.rolling(f"{cfg.smoothing_days}D", min_periods=cfg.smoothing_min_periods).mean()
        frame["price_index_smoothed"] = frame["date"].map(smoothed)
        frame["product"] = product
        frame["data_quality_flag"] = _flags(frame, product_ref_end(baselines, product, cfg), required)
        frames.append(frame)
    if not frames:
        raise ValueError("No included items produced any price data")
    out = pd.concat(frames, ignore_index=True)
    out = out.merge(premises_per_day, on=["product", "date"], how="left")
    out["n_premises"] = out["n_premises"].fillna(0).astype("int64")
    return out[INDEX_COLUMNS].sort_values(["product", "date"], ignore_index=True), baselines


def premises_per_day(observations: pd.DataFrame, items: pd.DataFrame) -> pd.DataFrame:
    valid = observations[~observations["outlier_flag"]].merge(items, on="item_code")
    return valid.groupby(["product", "date"], as_index=False)["premise_code"].nunique().rename(columns={"premise_code": "n_premises"})


def missing_days(index: pd.DataFrame) -> dict[str, list[str]]:
    """Calendar days with no index value between each product's first and last date."""
    out = {}
    for product, g in index.groupby("product"):
        full = pd.date_range(g["date"].min(), g["date"].max(), freq="D")
        out[product] = [d.date().isoformat() for d in full.difference(pd.DatetimeIndex(g["date"]))]
    return out


def plot_indexes(index: pd.DataFrame, cfg: IndexConfig, out_dir) -> list:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    out_dir.mkdir(parents=True, exist_ok=True)
    paths = []
    for product, g in index.groupby("product"):
        fig, ax = plt.subplots(figsize=(10, 4.5))
        ax.plot(g["date"], g["price_index_raw"], lw=0.7, alpha=0.5, label="raw (normalised)")
        ax.plot(g["date"], g["price_index_smoothed"], lw=1.6, label="smoothed (trailing 7d)")
        ax.plot(g["date"], g["price_index_chained"], lw=1.2, ls="--", label="chained (extra)")
        if cfg.per_item_days is None:
            ax.axvspan(cfg.ref_start, cfg.ref_end, color="grey", alpha=0.15, label="normalisation reference period")
        ax.set_title(f"{product}: price index (100 = reference-period median)")
        ax.set_ylabel("index")
        ax.legend(loc="best", fontsize=8)
        fig.autofmt_xdate()
        fig.tight_layout()
        p = out_dir / f"price_index_{product}.png"
        fig.savefig(p, dpi=120)
        plt.close(fig)
        paths.append(p)
    return paths


def write_outputs(paths, index: pd.DataFrame, baselines: pd.DataFrame, cfg: IndexConfig) -> None:
    ends = {p: product_ref_end(baselines, p, cfg) for p in index["product"].unique()}
    ref_end = min(ends.values())
    paths.processed.mkdir(parents=True, exist_ok=True)
    paths.stats.mkdir(parents=True, exist_ok=True)
    index.to_parquet(paths.price_index, index=False)
    baselines.to_csv(paths.index_item_baselines, index=False)
    stats = {
        "baseline_mode": "fixed_window" if cfg.per_item_days is None else f"per_item_first_{cfg.per_item_days}_days",
        "reference_window": [cfg.ref_start.date().isoformat(), ref_end.date().isoformat()] if cfg.per_item_days is None else None,
        "reference_end_earliest": ref_end.date().isoformat(),
        "point_in_time_valid_from": (ref_end + pd.Timedelta(days=1)).date().isoformat(),
        "point_in_time_valid_from_by_product": {p: (r + pd.Timedelta(days=1)).date().isoformat() for p, r in ends.items()},
        "min_ref_days": cfg.min_ref_days,
        "smoothing": f"trailing {cfg.smoothing_days}D, min_periods={cfg.smoothing_min_periods}",
        "rows": int(len(index)),
        "per_product": {
            p: {
                "first_date": g["date"].min().date().isoformat(),
                "last_date": g["date"].max().date().isoformat(),
                "days": int(len(g)),
                "items_eligible": int(baselines[(baselines["product"] == p) & baselines["eligible"]].shape[0]),
                "items_excluded_no_baseline": [int(c) for c in baselines[(baselines["product"] == p) & ~baselines["eligible"]]["item_code"]],
            }
            for p, g in index.groupby("product")
        },
        "missing_days": missing_days(index),
    }
    (paths.stats / "price_index.json").write_text(json.dumps(stats, indent=2))
