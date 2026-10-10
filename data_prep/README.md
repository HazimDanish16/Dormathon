# data_prep: staple-food price and news data pipeline

Everything that builds the datasets consumed by the app (`news_clean`, `price_index`, `item_mapping`, `examples`). Self-contained: install with `pip install -e ".[dev]"` from this folder. Full details, schemas, limits and regeneration steps: [DATA_HANDOVER.md](DATA_HANDOVER.md).

Not committed (too large, regenerate with the scripts): `data/contract/news_clean.parquet` (272 MB, above GitHub's 100 MB file limit) and all raw/processed parquet files.
