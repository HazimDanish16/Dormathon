"""Single place that defines where every data artefact lives."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ..config import get_settings


@dataclass(frozen=True)
class DataPaths:
    root: Path

    @classmethod
    def default(cls) -> "DataPaths":
        return cls(get_settings().data_dir)

    # raw ------------------------------------------------------------
    @property
    def raw_prices(self) -> Path:
        return self.root / "raw" / "pricecatcher"

    @property
    def raw_prices_full(self) -> Path:
        """Temporary full monthly downloads (deleted once filtered)."""
        return self.raw_prices / "full"

    @property
    def raw_price_items(self) -> Path:
        """Per-month files holding only candidate items (kept, small)."""
        return self.raw_prices / "items"

    @property
    def raw_news(self) -> Path:
        return self.root / "raw" / "news"

    @property
    def legacy_news_csv(self) -> Path:
        return self.root / "news" / "news_v1.csv"

    @property
    def lookup_item(self) -> Path:
        return self.raw_prices / "lookup_item.parquet"

    @property
    def lookup_premise(self) -> Path:
        return self.raw_prices / "lookup_premise.parquet"

    @property
    def download_log(self) -> Path:
        return self.raw_prices / "download_log.jsonl"

    # processed --------------------------------------------------------
    @property
    def processed(self) -> Path:
        return self.root / "processed"

    @property
    def stats(self) -> Path:
        return self.processed / "stats"

    @property
    def item_mapping(self) -> Path:
        return self.processed / "item_mapping.csv"

    @property
    def price_observations(self) -> Path:
        return self.processed / "price_observations.parquet"

    @property
    def daily_item_prices(self) -> Path:
        return self.processed / "daily_item_prices.parquet"

    @property
    def price_index(self) -> Path:
        return self.processed / "price_index.parquet"

    @property
    def index_item_baselines(self) -> Path:
        return self.processed / "index_item_baselines.csv"

    @property
    def historical_news(self) -> Path:
        return self.processed / "historical_news.parquet"

    @property
    def quality_report_json(self) -> Path:
        return self.processed / "data_quality_report.json"

    # reports ----------------------------------------------------------
    @property
    def reports(self) -> Path:
        return self.root / "reports"

    @property
    def plots(self) -> Path:
        return self.reports / "plots"

    @property
    def item_mapping_review(self) -> Path:
        return self.reports / "item_mapping_review.csv"

    @property
    def rejected_prices(self) -> Path:
        return self.reports / "rejected_price_observations.parquet"

    @property
    def rejected_news(self) -> Path:
        return self.reports / "rejected_news.csv"

    @property
    def quality_report_md(self) -> Path:
        return self.reports / "data_quality_report.md"

    @property
    def overlap_report_md(self) -> Path:
        return self.reports / "dataset_overlap.md"

    def ensure(self) -> None:
        for d in (
            self.raw_prices_full,
            self.raw_price_items,
            self.raw_news,
            self.stats,
            self.plots,
        ):
            d.mkdir(parents=True, exist_ok=True)
