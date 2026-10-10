"""Cleaning of the Kaggle news corpus (The Star, English).

Facts verified on the real file (2026-10-10): 13 columns, every `published_date`
is "YYYY-MM-DD 00:00:00" (a date with no time of day) and matches the date in the
article URL path. So timestamps carry NO time of day: we store them as midnight
Asia/Kuala_Lumpur placeholders and say so (`is_date_only`). Downstream code must
treat an article dated D as available only after D (end of day), never at a
specific hour.

The corpus is NOT filtered by topic; relevance filtering belongs to the ML stage.
Original columns are preserved; cleaned fields are added alongside them.
"""

from __future__ import annotations

import html
import json
import re
import unicodedata
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from urllib.parse import urlsplit

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

TZ = "Asia/Kuala_Lumpur"
PRD_COLUMNS = [
    "content_id",
    "title",
    "text",
    "section",
    "category",
    "content_tier",
    "content_length",
    "authors",
    "published_date",
    "keywords",
    "summary",
    "url",
]
OPTIONAL_COLUMNS = ["top_image"]
ADDED_COLUMNS = ["published_at", "published_date_local", "is_date_only", "url_normalized", "title_clean", "text_clean", "text_chars"]

NEWS_SCHEMA = pa.schema(
    [pa.field(c, pa.string()) for c in PRD_COLUMNS + OPTIONAL_COLUMNS]
    + [
        pa.field("published_at", pa.timestamp("ns", tz=TZ)),
        pa.field("published_date_local", pa.date32()),
        pa.field("is_date_only", pa.bool_()),
        pa.field("url_normalized", pa.string()),
        pa.field("title_clean", pa.string()),
        pa.field("text_clean", pa.string()),
        pa.field("text_chars", pa.int32()),
    ]
)

_TAG = re.compile(r"<[^>]+>")
_SPACE = re.compile(r"\s+")
_ZW = dict.fromkeys(map(ord, "​‌‍﻿­"), None)
_URL_DATE = re.compile(r"/(20\d\d)/(\d\d)/(\d\d)(?:/|$)")
_TRACKING = re.compile(r"^(utm_|fbclid|gclid)", re.I)


class NewsSchemaError(RuntimeError):
    pass


class NewsTimezoneError(RuntimeError):
    pass


def clean_text(value: str) -> str:
    if not value:
        return ""
    s = html.unescape(str(value))
    s = _TAG.sub(" ", s)
    s = unicodedata.normalize("NFKC", s).translate(_ZW).replace("\xa0", " ")
    return _SPACE.sub(" ", s).strip()


def normalize_url(url: str) -> str:
    """Lowercase host (no www), drop fragment, query and trailing slash."""
    if not url:
        return ""
    parts = urlsplit(url.strip())
    host = parts.netloc.lower()
    if host.startswith("www."):
        host = host[4:]
    path = re.sub(r"/{2,}", "/", parts.path).rstrip("/")
    return f"{host}{path}".lower()


def normalize_title(title: str) -> str:
    s = unicodedata.normalize("NFKC", clean_text(title)).casefold()
    return _SPACE.sub(" ", re.sub(r"[^\w\s]", " ", s)).strip()


def url_date(url: str) -> date | None:
    m = _URL_DATE.search(url or "")
    if not m:
        return None
    try:
        return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    except ValueError:
        return None


@dataclass
class TimeConvention:
    name: str  # date_only | tz_aware | local_time | utc_time
    match_asis: float | None
    match_plus8: float | None
    sample_rows: int

    def to_dict(self) -> dict:
        return self.__dict__.copy()


def infer_convention(sample: pd.DataFrame, threshold: float = 0.95) -> TimeConvention:
    """Decide how to read published_date. Never assumes naive == Malaysia time:
    the choice must be supported by the article URL dates, otherwise we stop."""
    parsed = pd.to_datetime(sample["published_date"], errors="coerce", format="ISO8601")
    ok = parsed.notna()
    if ok.sum() == 0:
        raise NewsTimezoneError("No parseable published_date values in the sample")
    parsed = parsed[ok]
    urls = sample.loc[ok, "url"].map(url_date)
    have = urls.notna()
    n = int(have.sum())

    def rate(ts: pd.Series) -> float | None:
        if n == 0:
            return None
        d = ts[have].dt.date
        return float((d.to_numpy() == urls[have].to_numpy()).mean())

    if getattr(parsed.dt, "tz", None) is not None:
        return TimeConvention("tz_aware", None, None, int(ok.sum()))
    midnight = ((parsed.dt.hour == 0) & (parsed.dt.minute == 0) & (parsed.dt.second == 0)).all()
    asis = rate(parsed)
    plus8 = rate(parsed + pd.Timedelta(hours=8))
    if midnight:
        if asis is not None and asis < threshold:
            raise NewsTimezoneError(f"Date-only timestamps agree with URL dates only {asis:.1%} of the time; cannot verify")
        return TimeConvention("date_only", asis, plus8, int(ok.sum()))
    if asis is not None and asis >= threshold and asis >= (plus8 or 0):
        return TimeConvention("local_time", asis, plus8, int(ok.sum()))
    if plus8 is not None and plus8 >= threshold:
        return TimeConvention("utc_time", asis, plus8, int(ok.sum()))
    raise NewsTimezoneError(
        f"Timestamps have a time of day but neither 'as-is' ({asis}) nor 'UTC+8' ({plus8}) matches URL dates; refusing to assume a timezone"
    )


def localize(parsed: pd.Series, convention: TimeConvention) -> pd.Series:
    if convention.name == "tz_aware":
        return parsed.dt.tz_convert(TZ)
    if convention.name == "utc_time":
        return parsed.dt.tz_localize("UTC").dt.tz_convert(TZ)
    return parsed.dt.tz_localize(TZ)  # date_only / local_time


def _check_schema(columns: list[str]) -> None:
    missing = [c for c in PRD_COLUMNS if c not in columns]
    if missing:
        raise NewsSchemaError(f"News file is missing columns {missing}; actual columns are {columns}")


def clean_news_csv(
    csv_path: Path,
    out_path: Path,
    rejected_path: Path,
    *,
    min_text_chars: int = 100,
    chunksize: int = 20_000,
    min_year: int = 2000,
    today: date | None = None,
) -> dict:
    today = today or date.today()
    max_date = today + timedelta(days=1)
    header = pd.read_csv(csv_path, nrows=0, dtype=str).columns.tolist()
    _check_schema(header)
    sample = pd.read_csv(csv_path, nrows=20_000, dtype=str, keep_default_na=False)
    convention = infer_convention(sample)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    rejected_path.parent.mkdir(parents=True, exist_ok=True)
    writer = pq.ParquetWriter(out_path, NEWS_SCHEMA)
    seen_url: set[str] = set()
    seen_id: set[str] = set()
    seen_title: dict[str, list[int]] = {}
    rejects: list[dict] = []
    reasons: dict[str, int] = {}
    empty_counts = {c: 0 for c in header}
    rows_read = kept = 0
    per_year: dict[int, int] = {}
    first: date | None = None
    last: date | None = None

    def reject(row, why: str) -> None:
        reasons[why] = reasons.get(why, 0) + 1
        if len(rejects) < 200_000:
            rejects.append({"content_id": row.content_id, "published_date": row.published_date, "url": row.url, "reason": why})

    try:
        for chunk in pd.read_csv(csv_path, dtype=str, keep_default_na=False, chunksize=chunksize, on_bad_lines="skip"):
            rows_read += len(chunk)
            for c in header:
                empty_counts[c] += int((chunk[c].str.strip() == "").sum())
            for col in OPTIONAL_COLUMNS:
                if col not in chunk.columns:
                    chunk[col] = ""
            parsed = pd.to_datetime(chunk["published_date"], errors="coerce", format="ISO8601")
            local = localize(parsed, convention) if parsed.notna().any() else parsed
            title_clean = chunk["title"].map(clean_text)
            text_clean = chunk["text"].map(clean_text)
            url_norm = chunk["url"].map(normalize_url)
            keep = []
            for i, row in enumerate(chunk.itertuples(index=False)):
                ts = local.iloc[i]
                if pd.isna(ts) or not (min_year <= ts.year) or ts.date() > max_date:
                    reject(row, "unusable_date")
                    keep.append(False)
                    continue
                if len(text_clean.iloc[i]) < min_text_chars:
                    reject(row, "insufficient_text")
                    keep.append(False)
                    continue
                u = url_norm.iloc[i]
                cid = str(row.content_id).strip()
                if u and u in seen_url:
                    reject(row, "duplicate_url")
                    keep.append(False)
                    continue
                if cid and cid in seen_id:
                    reject(row, "duplicate_content_id")
                    keep.append(False)
                    continue
                t = normalize_title(title_clean.iloc[i])
                ordinal = ts.date().toordinal()
                if t and any(abs(ordinal - o) <= 1 for o in seen_title.get(t, ())):
                    reject(row, "near_duplicate_title")
                    keep.append(False)
                    continue
                if u:
                    seen_url.add(u)
                if cid:
                    seen_id.add(cid)
                if t:
                    seen_title.setdefault(t, []).append(ordinal)
                keep.append(True)
            mask = pd.Series(keep, index=chunk.index)
            if not mask.any():
                continue
            out = chunk[mask].copy()
            out["published_at"] = local[mask]
            out["published_date_local"] = local[mask].dt.date
            out["is_date_only"] = convention.name == "date_only"
            out["url_normalized"] = url_norm[mask]
            out["title_clean"] = title_clean[mask]
            out["text_clean"] = text_clean[mask]
            out["text_chars"] = text_clean[mask].str.len().astype("int32")
            table = pa.Table.from_pandas(out[[f.name for f in NEWS_SCHEMA]], schema=NEWS_SCHEMA, preserve_index=False)
            writer.write_table(table)
            kept += len(out)
            years = pd.Series(out["published_date_local"]).map(lambda d: d.year).value_counts()
            for y, n in years.items():
                per_year[int(y)] = per_year.get(int(y), 0) + int(n)
            lo, hi = min(out["published_date_local"]), max(out["published_date_local"])
            first = lo if first is None or lo < first else first
            last = hi if last is None or hi > last else last
    finally:
        writer.close()

    pd.DataFrame(rejects, columns=["content_id", "published_date", "url", "reason"]).to_csv(rejected_path, index=False)
    return {
        "source_file": csv_path.name,
        "columns": header,
        "time_convention": convention.to_dict(),
        "rows_read": rows_read,
        "rows_kept": kept,
        "rows_rejected": rows_read - kept,
        "rejected_by_reason": reasons,
        "empty_values_per_column": empty_counts,
        "min_text_chars": min_text_chars,
        "earliest_date": first.isoformat() if first else None,
        "latest_date": last.isoformat() if last else None,
        "articles_per_year": dict(sorted(per_year.items())),
        "dedup_rules": "normalised URL; content_id; normalised title within +-1 day (first occurrence kept)",
        "rejected_listing_truncated": len(rejects) >= 200_000,
    }


def write_stats(stats_dir: Path, stats: dict) -> None:
    stats_dir.mkdir(parents=True, exist_ok=True)
    (stats_dir / "clean_news.json").write_text(json.dumps(stats, indent=2, default=str))
