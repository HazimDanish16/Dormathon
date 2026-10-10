"""Export the three data-contract files the app repo (Dormathon) expects.

Writes to data/contract/: news_clean.parquet, price_index.parquet, item_mapping.csv.
examples.parquet (labels/returns) is NOT produced here: that is the modelling stage.
Copy the three files into the app repo's data/processed/.
"""
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from newsprice.dataprep.paths import DataPaths


def main() -> None:
    paths = DataPaths.default()
    out = paths.root / "contract"
    out.mkdir(parents=True, exist_ok=True)

    idx = pd.read_parquet(paths.price_index)
    idx = idx[idx["price_index_smoothed"].notna() & (idx["n_premises"] > 0) & ~idx["data_quality_flag"].str.contains("reference_period|no_eligible_items")]
    ex = pd.DataFrame({"product": idx["product"], "date": idx["date"].dt.normalize(), "index": idx["price_index_smoothed"].astype(float), "n_premises": idx["n_premises"].astype("int64")})
    ex.to_parquet(out / "price_index.parquet", index=False)

    mp = pd.read_csv(paths.item_mapping)
    mp = mp[mp["include"] == "yes"].rename(columns={"proposed_product": "product"})[["product", "item_code"]]
    mp.to_csv(out / "item_mapping.csv", index=False)

    schema = pa.schema([("article_id", pa.string()), ("title", pa.string()), ("summary", pa.string()), ("body", pa.string()),
                        ("source", pa.string()), ("url", pa.string()), ("language", pa.string()), ("published_at", pa.timestamp("ns", tz="UTC"))])
    cols = ["content_id", "title_clean", "text_clean", "url", "published_at", "summary"]
    pf = pq.ParquetFile(paths.historical_news)
    w = pq.ParquetWriter(out / "news_clean.parquet", schema)
    seen_ids: set[str] = set()
    seen_urls: set[str] = set()
    n = 0
    for batch in pf.iter_batches(batch_size=20000, columns=cols):
        d = batch.to_pandas()
        d["article_id"] = d["content_id"].astype(str)
        d = d[d["url"].str.startswith(("http://", "https://")) & d["article_id"].ne("") & ~d["article_id"].isin(seen_ids) & ~d["url"].isin(seen_urls)]
        d = d.drop_duplicates(["article_id"]).drop_duplicates(["url"])
        seen_ids.update(d["article_id"]); seen_urls.update(d["url"])
        o = pd.DataFrame({"article_id": d["article_id"], "title": d["title_clean"], "summary": d["summary"].fillna("").astype(str),
                          "body": d["text_clean"], "source": "The Star", "url": d["url"], "language": "en",
                          "published_at": d["published_at"].dt.tz_convert("UTC")})
        w.write_table(pa.Table.from_pandas(o, schema=schema, preserve_index=False))
        n += len(o)
    w.close()
    print(f"price_index rows {len(ex)}, item_mapping rows {len(mp)}, news rows {n} -> {out}")


if __name__ == "__main__":
    main()
