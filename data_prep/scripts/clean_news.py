"""Step 6. Clean the news CSV into data/processed/historical_news.parquet.

  python scripts/clean_news.py [path/to/news.csv]
"""
import sys
from pathlib import Path

from newsprice.dataprep.news_cleaning import clean_news_csv, write_stats
from newsprice.dataprep.paths import DataPaths


def main() -> None:
    paths = DataPaths.default()
    paths.ensure()
    if len(sys.argv) > 1:
        src = Path(sys.argv[1])
    elif paths.legacy_news_csv.exists():
        src = paths.legacy_news_csv
    else:
        found = sorted(paths.raw_news.glob("*.csv"))
        if not found:
            raise SystemExit("No news CSV found. Run scripts/download_news.py first.")
        src = found[0]
    stats = clean_news_csv(src, paths.historical_news, paths.rejected_news.with_suffix(".csv"))
    write_stats(paths.stats, stats)
    print(f"read {stats['rows_read']}, kept {stats['rows_kept']}, rejected {stats['rejected_by_reason']}")
    print(f"range {stats['earliest_date']}..{stats['latest_date']}; convention {stats['time_convention']['name']}")


if __name__ == "__main__":
    main()
