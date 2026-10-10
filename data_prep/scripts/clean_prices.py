"""Step 3. Clean prices and build daily item statistics. Requires an approved mapping.

  python scripts/clean_prices.py
"""
import pandas as pd

from newsprice.dataprep import price_cleaning as pc
from newsprice.dataprep.mapping import MappingNotApproved
from newsprice.dataprep.paths import DataPaths


def main() -> None:
    paths = DataPaths.default()
    if not paths.item_mapping.exists():
        raise SystemExit("Approve the mapping first: python scripts/map_items.py --approve")
    approved = pd.read_csv(paths.item_mapping)
    if not approved["include"].isin(["yes", "no"]).all():
        raise MappingNotApproved("item_mapping.csv still has unresolved rows")
    keep = approved.loc[approved["include"] == "yes", "item_code"]
    obs = pc.read_item_observations(paths)
    obs = obs[obs["item_code"].isin(keep)]
    res = pc.clean_observations(obs)
    daily = pc.daily_item_stats(res.observations)
    pc.write_outputs(paths, res, daily)
    for k in ("rows_input", "rows_rejected_total", "rows_after_cleaning", "outliers_flagged", "rows_without_baseline"):
        print(f"{k}: {res.stats[k]}")
    print(f"rejected by reason: {res.stats['rejected_by_reason']}")
    print(f"daily item rows: {len(daily)}")


if __name__ == "__main__":
    main()
