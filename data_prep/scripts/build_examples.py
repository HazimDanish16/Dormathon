"""Build data/contract/examples.parquet from the contract news and price index.

  python scripts/build_examples.py [--horizon 14] [--min-premises 10]
Run scripts/export_contract.py first. Writes examples.parquet and examples_stats.json.
"""
import argparse
import json

import pandas as pd

from newsprice.dataprep.examples import build_examples
from newsprice.dataprep.paths import DataPaths


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--horizon", type=int, default=14)
    ap.add_argument("--min-premises", type=int, default=10)
    ap.add_argument("--exclude-products", nargs="*", default=["cooking_oil"], help="products dropped for too few examples")
    args = ap.parse_args()
    out_dir = DataPaths.default().root / "contract"
    news = pd.read_parquet(out_dir / "news_clean.parquet", columns=["article_id", "title", "summary", "body", "published_at"])
    index = pd.read_parquet(out_dir / "price_index.parquet")
    ex, stats = build_examples(news, index, args.horizon, args.min_premises)
    ex = ex[~ex["product"].isin(args.exclude_products)].reset_index(drop=True)
    stats["excluded_products"] = args.exclude_products
    stats["per_product_after_exclusion"] = ex["product"].value_counts().to_dict()
    stats["examples_after_exclusion"] = int(len(ex))
    ex.to_parquet(out_dir / "examples.parquet", index=False)
    (out_dir / "examples_stats.json").write_text(json.dumps(stats, indent=2, default=str))
    print(json.dumps(stats, indent=2, default=str))


if __name__ == "__main__":
    main()
