"""Resumable PriceCatcher download.

Each month is fetched in full, reduced to the candidate item codes (keeping
date, premise_code, item_code and price exactly as published), and the large
raw file is deleted. The reduced per-month file, the source URL and a download
log line are kept for audit.

Network failures retry with exponential backoff; an interrupted download
resumes from the partial file using an HTTP Range request.
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

import httpx
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from .paths import DataPaths

log = logging.getLogger(__name__)

BASE_URL = "https://storage.data.gov.my/pricecatcher"
LOOKUP_ITEM_URL = f"{BASE_URL}/lookup_item.parquet"
LOOKUP_PREMISE_URL = f"{BASE_URL}/lookup_premise.parquet"
REQUIRED_PRICE_COLUMNS = ("date", "premise_code", "item_code", "price")


class DownloadError(RuntimeError):
    pass


class SchemaError(RuntimeError):
    pass


class _Retryable(Exception):
    pass


def month_url(month: str) -> str:
    return f"{BASE_URL}/pricecatcher_{month}.parquet"


def months_between(start: str, end: str) -> list[str]:
    return [str(p) for p in pd.period_range(start=start, end=end, freq="M")]


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def http_download(
    url: str,
    dest: Path,
    *,
    client: httpx.Client | None = None,
    attempts: int = 5,
    backoff: float = 2.0,
    sleep: Callable[[float], None] = time.sleep,
) -> dict:
    """Download url to dest, resuming a partial file. Returns a status dict.

    status is "ok" or "unavailable" (HTTP 404). Other failures raise
    DownloadError after `attempts` tries.
    """
    dest.parent.mkdir(parents=True, exist_ok=True)
    part = dest.with_suffix(dest.suffix + ".part")
    own_client = client is None
    client = client or httpx.Client(timeout=httpx.Timeout(60.0, read=120.0), follow_redirects=True)
    last_error: Exception | None = None
    try:
        for attempt in range(1, attempts + 1):
            try:
                resume_from = part.stat().st_size if part.exists() else 0
                headers = {"Range": f"bytes={resume_from}-"} if resume_from else {}
                with client.stream("GET", url, headers=headers) as resp:
                    code = resp.status_code
                    if code == 404:
                        return {"status": "unavailable", "http_status": 404, "attempts": attempt}
                    if code == 416:  # stale or already-complete partial: start over
                        part.unlink(missing_ok=True)
                        raise _Retryable("416 range not satisfiable; restarting")
                    if code in (429, 500, 502, 503, 504):
                        raise _Retryable(f"HTTP {code}")
                    if code not in (200, 206):
                        raise DownloadError(f"HTTP {code} for {url}")
                    mode = "ab" if (code == 206 and resume_from) else "wb"
                    with part.open(mode) as fh:
                        for chunk in resp.iter_bytes(1 << 20):
                            fh.write(chunk)
                part.replace(dest)
                return {"status": "ok", "http_status": 200, "attempts": attempt, "bytes": dest.stat().st_size}
            except (httpx.TransportError, _Retryable) as exc:
                last_error = exc
                log.warning("Attempt %s/%s failed for %s: %s", attempt, attempts, url, exc)
                if attempt < attempts:
                    sleep(min(backoff * 2 ** (attempt - 1), 60.0))
        raise DownloadError(f"Giving up on {url} after {attempts} attempts: {last_error}")
    finally:
        if own_client:
            client.close()


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def _append_log(paths: DataPaths, record: dict) -> None:
    paths.download_log.parent.mkdir(parents=True, exist_ok=True)
    with paths.download_log.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record) + "\n")


def download_lookups(paths: DataPaths, client: httpx.Client | None = None, force: bool = False) -> dict[str, pd.DataFrame]:
    """Download lookup_item and lookup_premise, log them, and return both frames."""
    out = {}
    for name, url, dest in (
        ("lookup_item", LOOKUP_ITEM_URL, paths.lookup_item),
        ("lookup_premise", LOOKUP_PREMISE_URL, paths.lookup_premise),
    ):
        if force or not dest.exists():
            res = http_download(url, dest, client=client)
            if res["status"] != "ok":
                raise DownloadError(f"{name} unavailable at {url}: {res}")
            _append_log(paths, {"file": name, "url": url, "downloaded_at": _utcnow(), "sha256": _sha256(dest), **res})
        out[name] = pd.read_parquet(dest)
    return out


def filter_month(raw_path: Path, item_codes: list[int]) -> tuple[pa.Table, int]:
    """Read only the needed columns/rows from a monthly parquet. Returns (table, total_rows)."""
    pf = pq.ParquetFile(raw_path)
    names = pf.schema_arrow.names
    missing = [c for c in REQUIRED_PRICE_COLUMNS if c not in names]
    if missing:
        raise SchemaError(f"{raw_path.name}: missing columns {missing}; actual columns are {names}")
    total = pf.metadata.num_rows
    table = pq.read_table(raw_path, columns=list(REQUIRED_PRICE_COLUMNS), filters=[("item_code", "in", list(item_codes))])
    return table, total


@dataclass
class AcquisitionSummary:
    requested: list[str]
    downloaded: list[str] = field(default_factory=list)
    skipped_existing: list[str] = field(default_factory=list)
    unavailable: list[str] = field(default_factory=list)
    failed: dict[str, str] = field(default_factory=dict)
    rows_kept: int = 0

    def to_dict(self) -> dict:
        return {
            "requested_months": self.requested,
            "downloaded": self.downloaded,
            "skipped_existing": self.skipped_existing,
            "unavailable_404": self.unavailable,
            "failed": self.failed,
            "rows_kept": self.rows_kept,
            "source_files_ok": len(self.downloaded) + len(self.skipped_existing),
            "pattern": f"{BASE_URL}/pricecatcher_YYYY-MM.parquet",
        }


def acquire_prices(
    paths: DataPaths,
    months: list[str],
    item_codes: list[int],
    *,
    keep_raw: bool = False,
    force: bool = False,
    client: httpx.Client | None = None,
    sleep: Callable[[float], None] = time.sleep,
) -> AcquisitionSummary:
    """Download, filter and log each month. One bad month never stops the rest."""
    paths.ensure()
    summary = AcquisitionSummary(requested=months)
    for month in months:
        items_file = paths.raw_price_items / f"pricecatcher_items_{month}.parquet"
        url = month_url(month)
        if items_file.exists() and not force:
            summary.skipped_existing.append(month)
            continue
        raw = paths.raw_prices_full / f"pricecatcher_{month}.parquet"
        try:
            res = http_download(url, raw, client=client, sleep=sleep)
            if res["status"] == "unavailable":
                summary.unavailable.append(month)
                _append_log(paths, {"month": month, "url": url, "status": "unavailable", "downloaded_at": _utcnow(), **res})
                log.warning("%s not published (404)", month)
                continue
            try:
                table, total = filter_month(raw, item_codes)
            except (pa.ArrowInvalid, OSError):
                raw.unlink(missing_ok=True)  # corrupt download: fetch once more
                http_download(url, raw, client=client, sleep=sleep)
                table, total = filter_month(raw, item_codes)
            pq.write_table(table, items_file)
            _append_log(
                paths,
                {
                    "month": month,
                    "url": url,
                    "status": "ok",
                    "downloaded_at": _utcnow(),
                    "bytes": raw.stat().st_size,
                    "sha256": _sha256(raw),
                    "rows_total": total,
                    "rows_kept": table.num_rows,
                    "items_file": str(items_file.name),
                },
            )
            summary.downloaded.append(month)
            summary.rows_kept += table.num_rows
            if not keep_raw:
                raw.unlink(missing_ok=True)
            log.info("%s: kept %s of %s rows", month, table.num_rows, total)
        except (DownloadError, SchemaError, pa.ArrowException, OSError) as exc:
            summary.failed[month] = str(exc)
            _append_log(paths, {"month": month, "url": url, "status": "failed", "error": str(exc), "downloaded_at": _utcnow()})
            log.error("%s failed: %s", month, exc)
    (paths.stats / "download_summary.json").write_text(json.dumps(summary.to_dict(), indent=2))
    return summary
