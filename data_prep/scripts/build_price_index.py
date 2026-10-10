"""Step 4. Build the four product price indexes + plots.

  python scripts/build_price_index.py [--ref-start 2023-07-01 --ref-end 2023-09-30]
Default: each item is normalised by its own first 90 days and joins the index afterwards.
--fixed-window uses one shared window (--ref-start/--ref-end) instead.
"""
import argparse

import pandas as pd

from newsprice.dataprep.mapping import included_items
from newsprice.dataprep.paths import DataPaths
from newsprice.dataprep import price_index as pi


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ref-start", default="2023-07-01")
    ap.add_argument("--ref-end", default="2023-09-30")
    ap.add_argument("--min-ref-days", type=int, default=30)
    ap.add_argument("--fixed-window", action="store_true")
    ap.add_argument("--per-item-days", type=int, default=90)
    ap.add_argument("--no-plots", action="store_true")
    args = ap.parse_args()
    paths = DataPaths.default()
    daily = pd.read_parquet(paths.daily_item_prices)
    obs = pd.read_parquet(paths.price_observations)
    items = included_items(pd.read_csv(paths.item_mapping))
    cfg = pi.IndexConfig.from_strings(args.ref_start, args.ref_end, min_ref_days=args.min_ref_days, per_item_days=None if args.fixed_window else args.per_item_days)
    ppd = pi.premises_per_day(obs, items)
    index, baselines = pi.build_price_index(daily, items, ppd, cfg)
    paths.ensure()
    pi.write_outputs(paths, index, baselines, cfg)
    if not args.no_plots:
        for p in pi.plot_indexes(index, cfg, paths.plots):
            print("plot:", p)
    print(index.groupby("product").agg(first=("date", "min"), last=("date", "max"), days=("date", "size")).to_string())
    print("excluded (no baseline):", baselines[~baselines["eligible"]][["product", "item_code"]].values.tolist())


if __name__ == "__main__":
    main()
