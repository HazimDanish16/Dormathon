"""Step 2. Download PriceCatcher months (resumable) and keep only candidate items.

  python scripts/download_prices.py --start 2023-07 [--end 2026-09] [--keep-raw] [--force]
Needs data/processed/../reports/item_mapping_review.csv (run map_items.py first).
"""
import argparse
import logging

import pandas as pd

from newsprice.dataprep.download import acquire_prices, months_between
from newsprice.dataprep.mapping import candidate_item_codes
from newsprice.dataprep.paths import DataPaths


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", default="2023-07")
    ap.add_argument("--end", default=None, help="default: current month")
    ap.add_argument("--keep-raw", action="store_true")
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO)
    paths = DataPaths.default()
    if not paths.item_mapping_review.exists():
        raise SystemExit("Run scripts/map_items.py first.")
    codes = candidate_item_codes(pd.read_csv(paths.item_mapping_review))
    end = args.end or str(pd.Timestamp.now().to_period("M"))
    summary = acquire_prices(paths, months_between(args.start, end), codes, keep_raw=args.keep_raw, force=args.force)
    d = summary.to_dict()
    print(f"downloaded {len(d['downloaded'])}, skipped {len(d['skipped_existing'])}, unavailable {d['unavailable_404']}, failed {len(d['failed'])}, rows kept {d['rows_kept']}")
    for m, e in d["failed"].items():
        print(f"  FAILED {m}: {e}")
    print("Re-run the same command to retry failed months.")


if __name__ == "__main__":
    main()
