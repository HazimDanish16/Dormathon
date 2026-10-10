"""Step 1. Download lookup tables, write the item-mapping review file, or approve it.

  python scripts/map_items.py                      # writes data/reports/item_mapping_review.csv
  python scripts/map_items.py --approve            # needs every 'review' row resolved by hand
  python scripts/map_items.py --approve --accept-suggestions   # take suggested_include for review rows
"""
import argparse
import logging

import pandas as pd

from newsprice.dataprep.download import download_lookups
from newsprice.dataprep.mapping import approve_mapping, build_mapping, MappingNotApproved
from newsprice.dataprep.paths import DataPaths


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--approve", action="store_true")
    ap.add_argument("--accept-suggestions", action="store_true")
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO)
    paths = DataPaths.default()
    paths.ensure()
    if not args.approve:
        lookups = download_lookups(paths)
        review = build_mapping(lookups["lookup_item"])
        review.to_csv(paths.item_mapping_review, index=False)
        print(f"Wrote {paths.item_mapping_review} ({len(review)} candidate items)")
        print(review.groupby(["proposed_product", "include"]).size().to_string())
        pending = review[review["include"] == "review"]
        for r in pending.itertuples():
            print(f"  REVIEW {r.item_code} {r.item} [{r.unit}] suggested={r.suggested_include}: {r.review_note}")
        print("Open the CSV, set 'include' to yes/no for each 'review' row, then run with --approve.")
        return
    review = pd.read_csv(paths.item_mapping_review)
    try:
        approved = approve_mapping(review, accept_suggestions=args.accept_suggestions)
    except MappingNotApproved as exc:
        raise SystemExit(str(exc))
    approved.to_csv(paths.item_mapping, index=False)
    print(f"Wrote {paths.item_mapping}")
    print(approved[approved["include"] == "yes"].groupby("proposed_product").size().to_string())


if __name__ == "__main__":
    main()
