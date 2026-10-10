"""Consolidated data-quality and dataset-overlap reports."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from .checks import Check
from .paths import DataPaths

HORIZONS = (7, 14, 28)


def _read_json(path: Path) -> dict | None:
    return json.loads(path.read_text()) if path.exists() else None


def compute_overlap(news_first: str | None, news_last: str | None, index: pd.DataFrame | None, pit_start: str | None) -> dict:
    if not (news_first and news_last) or index is None or index.empty or not pit_start:
        return {"available": False, "reason": "news or price index missing"}
    px_first, px_last = index["date"].min().date().isoformat(), index["date"].max().date().isoformat()
    start = max(news_first, pit_start)  # ISO dates compare lexicographically
    end = min(news_last, px_last)
    out = {
        "available": start <= end,
        "news_range": [news_first, news_last],
        "price_index_range": [px_first, px_last],
        "price_index_point_in_time_from": pit_start,
        "overlap": [start, end] if start <= end else None,
        "usable_news_end_for_outcome_horizon_days": {},
    }
    last_px = pd.Timestamp(px_last)
    for h in HORIZONS:
        out["usable_news_end_for_outcome_horizon_days"][str(h)] = min(pd.Timestamp(news_last), last_px - pd.Timedelta(days=h)).date().isoformat()
    return out


def build_report(paths: DataPaths, checks: list[Check] | None = None) -> dict:
    stats = {
        "download": _read_json(paths.stats / "download_summary.json"),
        "price_cleaning": _read_json(paths.stats / "clean_prices.json"),
        "price_index": _read_json(paths.stats / "price_index.json"),
        "news": _read_json(paths.stats / "clean_news.json"),
    }
    index = pd.read_parquet(paths.price_index) if paths.price_index.exists() else None
    mapping = pd.read_csv(paths.item_mapping) if paths.item_mapping.exists() else None
    report: dict = {"generated_from": "data/processed/stats/*.json and processed datasets", **stats}

    if paths.download_log.exists():
        lines = [json.loads(x) for x in paths.download_log.read_text().splitlines() if x.strip()]
        ok_months = sorted({r["month"] for r in lines if r.get("status") == "ok" and "month" in r})
        report["download_log_months_ok"] = ok_months
        report["download_log_months_unavailable"] = sorted({r["month"] for r in lines if r.get("status") == "unavailable"})

    if index is not None:
        index = index.copy()
        index["month"] = index["date"].dt.to_period("M").astype(str)
        report["coverage_by_month"] = {
            p: g.groupby("month").agg(days=("date", "nunique"), median_items=("n_items", "median"), median_premises=("n_premises", "median")).round(1).to_dict("index")
            for p, g in index.groupby("product")
        }
    if paths.daily_item_prices.exists() and mapping is not None:
        daily = pd.read_parquet(paths.daily_item_prices)
        inc = mapping[mapping["include"] == "yes"][["item_code", "proposed_product"]]
        by_prod = daily.merge(inc, on="item_code").groupby("proposed_product").agg(
            valid_observations=("n_obs", "sum"), item_days=("date", "size"), first=("date", "min"), last=("date", "max")
        )
        report["valid_observations_by_product"] = {
            p: {"valid_observations": int(r.valid_observations), "item_days": int(r.item_days), "first": str(r["first"].date()), "last": str(r["last"].date())}
            for p, r in by_prod.iterrows()
        }
    news = stats["news"]
    pit = (stats["price_index"] or {}).get("point_in_time_valid_from")
    report["overlap"] = compute_overlap(news and news.get("earliest_date"), news and news.get("latest_date"), index, pit)
    if checks is not None:
        report["validation"] = {"passed": sum(c.passed for c in checks), "total": len(checks), "failures": [{"check": c.name, "detail": c.detail} for c in checks if not c.passed]}
    review = pd.read_csv(paths.item_mapping_review) if paths.item_mapping_review.exists() else None
    if review is not None:
        report["mapping_ambiguities"] = review[review["include"] == "review"][["item_code", "item", "suggested_include", "review_note"]].to_dict("records")
    return report


def _md_kv(d: dict | None) -> str:
    if not d:
        return "_not available (stage not run)_\n"
    return "\n".join(f"- **{k}**: {v}" for k, v in d.items() if not isinstance(v, (dict, list)) or len(str(v)) < 160) + "\n"


def write_reports(paths: DataPaths, report: dict) -> None:
    paths.processed.mkdir(parents=True, exist_ok=True)
    paths.reports.mkdir(parents=True, exist_ok=True)
    paths.quality_report_json.write_text(json.dumps(report, indent=2, default=str))

    dl, pc, pi, nw = report.get("download"), report.get("price_cleaning"), report.get("price_index"), report.get("news")
    md = ["# Data quality report\n"]
    md.append("## 1. Source files\n")
    md.append(f"- Months downloaded OK (from download log): {report.get('download_log_months_ok', 'n/a')}\n- Months unavailable (404): {report.get('download_log_months_unavailable', 'n/a')}\n")
    md.append(_md_kv(dl))
    md.append("## 2. Date coverage\n")
    if pc:
        md.append(f"- Prices (daily item table): {pc.get('first_date')} to {pc.get('last_date')}\n")
    if nw:
        md.append(f"- News: {nw.get('earliest_date')} to {nw.get('latest_date')} ({nw.get('time_convention', {}).get('name')} timestamps)\n")
    md.append("## 3. Price cleaning (rows before and after)\n")
    if pc:
        for k in ("rows_input", "rows_rejected_total", "rows_after_cleaning", "outliers_flagged", "rows_valid_for_stats", "rows_without_baseline", "exact_duplicates_dropped", "key_conflict_rows_rejected"):
            md.append(f"- {k}: {pc.get(k)}\n")
        md.append(f"- rejected by reason: {pc.get('rejected_by_reason')}\n- missing values in input: {pc.get('missing_values_input')}\n")
    else:
        md.append("_not run_\n")
    md.append("## 4. Valid observations by product\n")
    for p, v in (report.get("valid_observations_by_product") or {}).items():
        md.append(f"- {p}: {v['valid_observations']} observations over {v['item_days']} item-days ({v['first']} to {v['last']})\n")
    md.append("## 5. Coverage by month (index days / median items / median premises)\n")
    for p, months in (report.get("coverage_by_month") or {}).items():
        md.append(f"\n**{p}**\n\n| month | days | median items | median premises |\n|---|---|---|---|\n")
        md.extend(f"| {m} | {v['days']} | {v['median_items']} | {v['median_premises']} |\n" for m, v in months.items())
    md.append("\n## 6. Missing price days (index)\n")
    for p, days in ((pi or {}).get("missing_days") or {}).items():
        md.append(f"- {p}: {len(days)} missing day(s){': ' + ', '.join(days[:30]) + (' ...' if len(days) > 30 else '') if days else ''}\n")
    md.append("## 7. News cleaning\n")
    if nw:
        md.append(f"- rows read {nw['rows_read']}, kept {nw['rows_kept']}, rejected {nw['rows_rejected']}\n- rejected by reason: {nw['rejected_by_reason']}\n- articles per year: {nw['articles_per_year']}\n- dedup rules: {nw['dedup_rules']}\n")
    else:
        md.append("_not run_\n")
    md.append("## 8. Known limitations and unresolved ambiguities\n")
    md.append("- News `published_date` has no time of day (date only); same-day publication order is unknown.\n- PriceCatcher is a survey of premises, not a census; coverage varies by day and premise.\n- Product indexes mix brands and pack sizes by normalising each item to its own reference median.\n- Items without enough reference-window data are excluded from the raw index (listed in index_item_baselines.csv).\n")
    for a in report.get("mapping_ambiguities", []):
        md.append(f"- Mapping review item {a['item_code']} ({a['item']}): suggested `{a['suggested_include']}`: {a['review_note']}\n")
    if report.get("validation"):
        v = report["validation"]
        md.append(f"\n## 9. Validation\n\n{v['passed']}/{v['total']} checks passed.\n")
        for f in v["failures"]:
            md.append(f"- FAIL {f['check']}: {f['detail']}\n")
    paths.quality_report_md.write_text("".join(md))

    ov = report["overlap"]
    om = ["# Dataset overlap (news x prices)\n\n"]
    if ov.get("available"):
        om.append(f"- News: {ov['news_range'][0]} to {ov['news_range'][1]}\n- Price index: {ov['price_index_range'][0]} to {ov['price_index_range'][1]}\n- Price index is point-in-time valid from: {ov['price_index_point_in_time_from']}\n- **Overlap usable for modelling: {ov['overlap'][0]} to {ov['overlap'][1]}**\n\n")
        om.append("Last news date whose outcome window is fully covered by price data:\n\n")
        for h, d in ov["usable_news_end_for_outcome_horizon_days"].items():
            om.append(f"- {h}-day outcome: news up to {d}\n")
        om.append("\nNews timestamps are dates only; treat an article dated D as known after the end of D.\n")
    else:
        om.append(f"Overlap could not be computed: {ov.get('reason')}\n")
    paths.overlap_report_md.write_text("".join(om))
