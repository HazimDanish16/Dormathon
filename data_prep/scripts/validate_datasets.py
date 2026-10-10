"""Step 7. Run all dataset checks and write the quality + overlap reports. Exit 1 on failure."""
import sys

import pandas as pd
import pyarrow.parquet as pq

from newsprice.dataprep import checks as ck
from newsprice.dataprep import reports
from newsprice.dataprep.paths import DataPaths


def main() -> None:
    paths = DataPaths.default()
    results: list[ck.Check] = []
    approved = pd.read_csv(paths.item_mapping) if paths.item_mapping.exists() else None
    lookup = pd.read_parquet(paths.lookup_item) if paths.lookup_item.exists() else None
    if approved is not None:
        results += ck.check_mapping(approved, lookup)
    else:
        results.append(ck.Check("item_mapping exists", False, "missing"))
    if paths.price_observations.exists():
        results += ck.check_observations(pd.read_parquet(paths.price_observations), approved)
    if paths.daily_item_prices.exists():
        results += ck.check_daily(pd.read_parquet(paths.daily_item_prices))
    if paths.price_index.exists():
        import json
        st = json.loads((paths.stats / "price_index.json").read_text())
        results += ck.check_index(pd.read_parquet(paths.price_index), approved, pd.Timestamp(st["reference_end_earliest"]))
    if paths.historical_news.exists():
        cols = pq.ParquetFile(paths.historical_news).schema_arrow.names
        need = ["published_at", "published_date_local", "text_clean", "url_normalized", "content_id"]
        results += ck.check_news(pd.read_parquet(paths.historical_news, columns=need), all_columns=cols)
    report = reports.build_report(paths, results)
    reports.write_reports(paths, report)
    ok, total = ck.summarize(results)
    for c in results:
        if not c.passed:
            print(f"FAIL {c.name}: {c.detail}")
    print(f"{ok}/{total} checks passed. Reports in {paths.reports}")
    sys.exit(0 if ok == total else 1)


if __name__ == "__main__":
    main()
