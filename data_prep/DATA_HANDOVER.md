# HargaRadar data handover: staple-food prices and news

Scope: data preparation only for `rice`, `egg`, `cooking_oil`, `chicken`. No labels (UP/DOWN/STABLE), model, MCP server, LLM or inference code is produced or touched here. Built from the data-engineering brief and `PRD.md`. All figures below are from the real run on 2026-10-10.

## 1. Output files (paths relative to the repo root; on the dev PC the root is `C:\Users\adiba\Documents\news-price-mcp`)
| File | What |
|---|---|
| `data/processed/item_mapping.csv` | Approved item-code to product mapping (human-reviewed) |
| `data/processed/price_observations.parquet` | Cleaned premise-level prices (7,178,345 rows) |
| `data/processed/daily_item_prices.parquet` | Daily national statistics per item (27,340 rows) |
| `data/processed/price_index.parquet` | Daily index per product (3,648 rows) |
| `data/processed/index_item_baselines.csv` | Per-item baseline used by the index |
| `data/processed/historical_news.parquet` | Cleaned news, 153,653 articles (535 MB) |
| `data/processed/data_quality_report.json` | Machine-readable report |
| `data/reports/data_quality_report.md`, `dataset_overlap.md` | Human-readable reports |
| `data/reports/item_mapping_review.csv` | Mapping proposals with reasons |
| `data/reports/rejected_price_observations.parquet`, `rejected_news.csv` | Rejected rows with reasons |
| `data/reports/plots/price_index_<product>.png` | One plot per product |
| `data/processed/stats/*.json` | Stage statistics |
| `data/raw/pricecatcher/` | Lookups, per-month filtered files, `download_log.jsonl` (source URL, sha256, rows per month) |

Large data files are gitignored; do not commit them.

## 2. Schemas
**item_mapping.csv**: `item_code` int, `item`, `unit`, `item_group`, `item_category`, `proposed_product`, `include` (yes/no only), `review_note`, `variant`, `suggested_include`, `approval` (`reviewed` | `suggestion_accepted`).

**price_observations.parquet**: `date` datetime, `premise_code` int, `item_code` int, `price` float (RM, as published), `baseline_median` float (median of the item's daily medians over the previous 30 days, current day excluded; NaN if no baseline), `baseline_ok` bool, `outlier_flag` bool, `source_month` str.

**daily_item_prices.parquet**: `date`, `item_code`, `median_price`, `p25_price`, `p75_price`, `n_premises`, `n_obs`, `n_outliers_flagged`. Outlier-flagged rows are excluded from the statistics. Sorted by item then date; one row per (item, date).

**price_index.parquet**: `date`, `product`, `price_index_raw` (per-item-normalised, x100), `price_index_smoothed` (trailing 7-day mean of raw over days with at least min(3, eligible items) items observed, min 3 such dates; NaN on `low_items` days), `price_index_chained` (extra series, starts at 100, built from the mean of day-to-day log returns; drifts with data gaps and composition changes, prefer smoothed), `n_items`, `n_items_chained`, `n_premises`, `data_quality_flag` (`;`-joined: `ok`, `reference_period`, `no_eligible_items`, `low_items`, `composition_change`, `gap_after_missing_days`). Only days with price data appear; missing calendar days are listed in `stats/price_index.json`.

**historical_news.parquet**: the 13 original Kaggle columns (`content_id, title, text, section, category, content_tier, content_length, authors, published_date, keywords, summary, url, top_image`, strings, unaltered) plus `published_at` (timestamp, tz Asia/Kuala_Lumpur), `published_date_local` (date), `is_date_only` (bool, always True here), `url_normalized`, `title_clean`, `text_clean`, `text_chars` (int).

## 3. Row counts and coverage
- Prices: 39 monthly files, 2023-07 to 2026-09 (2026-10 returns 404, not yet published). 11,818,871 rows kept after filtering to candidate items; 7,178,345 for approved items. Daily table spans 2023-07-01 to 2026-09-24.
- Index days by product: chicken 1,113 (first 2023-07-01), egg 1,108, rice 861 (from 2023-07-03), cooking_oil 566. Cooking oil has 613 missing calendar days (its items are surveyed sparsely); chicken 69, egg 74.
- News: 154,445 rows read, 153,653 kept, range 2020-10-31 to 2026-10-09. By year: 2020: 1, 2023: 79, 2024: 50,643, 2025: 56,523, 2026: 46,407. In practice usable news starts around 2023-12, not 2020.
- Overlap usable for modelling: 2023-10-01 to 2026-09-24 nominally, but the news is thin before ~2023-12. Point-in-time index valid from 2023-09-29 (chicken, egg, cooking_oil) and 2023-10-01 (rice). For a 14-day outcome, use news up to 2026-09-10 (7-day: 2026-09-17; 28-day: 2026-08-27).

## 4. Approved item-code mappings (`include = yes`; names are in `item_mapping.csv`)
- **rice (19)**: 904, 992, 1445, 1581, 1582, 1583, 1822, 1823, 1824, 1825, 1826, 1832, 1833, 1902, 1903, 1951, 2004, 2066, 2068. Branded 10kg bags. Item 1903 has no observations; 18 are in the index.
- **egg (6)**: 118, 119, 120, 1109, 1110, 1111. Hen eggs by grade and pack size.
- **cooking_oil (27)**: 254, 257, 260, 263, 266, 267, 1091-1095, 1100, 1101, 1598-1602, 1934-1942. Branded blended (sebatian) and pure palm (tulen) oil.
- **chicken (2)**: 1, 2. Whole dressed chicken per kg.
- **Excluded after review**: live chicken (3), old hen live (1364), kampung eggs (1930), subsidised 1kg packet oil (918), plus pulut and basmati rice, quail/duck/salted eggs, turkey, chicken parts, corn oil. Review rows were decided on 2026-10-10 by taking the suggested value (`approval = suggestion_accepted`), approved by ADIB.

## 5. Cleaning decisions
- Raw prices are never altered. Rejections (invalid date/key, null, non-numeric, non-finite, zero/negative price) go to `rejected_price_observations.parquet` with a reason; this run rejected 0 rows. Exact duplicates are dropped (0 found); conflicting duplicate keys are all rejected (0 found).
- Outliers: price > 3x or < 1/3 of the item's median daily price over the preceding 90 days (current day excluded, so no future data). Needs 3 observed days of history (weekly-surveyed items rarely have 10 in 30 days). 399 flagged; they stay in the file with `outlier_flag = True`. 1,267,855 rows (18%) have no baseline yet and are kept unflagged.
- No interpolation or forward fill anywhere.
- Index: each item is divided by its own median over its first 90 days (at least 20 observed days; the default of 30 excluded 16 rice items surveyed on only 22-29 days), x100, then averaged over items observed that day. An item joins the index the day after its own 90 days end, so no baseline uses future data. `--fixed-window` gives the brief's single shared window instead.
- News: HTML stripped and Unicode normalised into `*_clean` columns. Dedupe by normalised URL, `content_id`, and normalised title within +-1 day (first kept); 792 rows rejected (446 near-duplicate title, 344 duplicate URL, 2 unusable date). Articles under 100 characters of text are rejected (0 this run). No topic filtering: relevance filtering belongs to the ML stage.
- Timestamps: the Kaggle `published_date` is always `YYYY-MM-DD 00:00:00` and matches the date in the article URL (100% on a 20,000-row sample), so it is a date with no time of day. It is stored as midnight Asia/Kuala_Lumpur with `is_date_only = True`. The converter refuses to guess a timezone if URL dates disagree.

## 6. Known limitations
- PriceCatcher is a premise survey, not a census; coverage varies by day and premise. It is price surveillance data; official inflation figures come from DOSM CPI.
- Index days only exist where data exist (cooking oil: 613 missing days). Smooth only over observed dates.
- Rice baselines rest on 20-29 observed days per item; the rice raw index is noisier early on.
- Product indexes mix brands and pack sizes; each item is normalised to itself first.
- The subsidised status of "MINYAK MASAK PAKET" is inferred from the name, not stated in the lookup. Rice local/imported origin is not stated either.
- News timestamps have no time of day: treat an article dated D as known only after D ends. News is The Star only, and effectively starts in late 2023. The Star's robots.txt forbids scraping and ML training without written permission: disclose this in the submission. PriceCatcher is CC BY 4.0; the Kaggle uploader lists Apache 2.0.
- Earlier modelling experiments found news text adds no lift over price momentum (see `FINDING_news_vs_momentum.md`); that is outside this data-prep deliverable.

## 7. Regenerate everything (from the repo root)
```
pip install -e ".[dev]"
python scripts/map_items.py                                  # writes data/reports/item_mapping_review.csv
python scripts/map_items.py --approve [--accept-suggestions]  # needs review rows resolved
python scripts/download_prices.py --start 2023-07            # resumable; re-run to retry failed months
python scripts/clean_prices.py
python scripts/build_price_index.py --min-ref-days 20       # add --fixed-window for the brief's method
python scripts/download_news.py                              # or place the CSV at data/news/news_v1.csv
python scripts/clean_news.py
python scripts/validate_datasets.py                          # 41 checks, writes the reports
python -m pytest tests -q                                    # offline tests, synthetic data only
```
`python scripts/export_contract.py` writes `data/contract/{news_clean.parquet, price_index.parquet, item_mapping.csv}` in the column layout the app repo (HazimDanish16/Dormathon) expects (`index` = smoothed index, reference-period and no-item days dropped; `examples.parquet` is the modelling stage's job). Copy them into that repo's `data/processed/`.



## 8. Integration guide for the ML developer
```python
import pandas as pd
idx   = pd.read_parquet("data/processed/price_index.parquet")        # date, product, ...
daily = pd.read_parquet("data/processed/daily_item_prices.parquet")
news  = pd.read_parquet("data/processed/historical_news.parquet",
                        columns=["content_id", "title_clean", "text_clean", "published_date_local", "url_normalized"])
news["published_date_local"] = pd.to_datetime(news["published_date_local"])
mapping = pd.read_csv("data/processed/item_mapping.csv")
```
- The news file is 535 MB; always pass `columns=`.
- Use `price_index_smoothed` as the main series (raw is the noisy input, chained is an extra). Drop rows whose `data_quality_flag` contains `reference_period` or `no_eligible_items` before using the index values.
- Look-ahead rules: an article dated D is usable from D+1. For a base price use the index on or before D, and never use index values after the article date as features. Use a time split with a purge gap at least as long as the outcome horizon.
- Join news to products yourself (alias match on `title_clean` / `text_clean`); the news file is not product-filtered.
- Read `data/reports/dataset_overlap.md` for the safe date range per outcome horizon.

## 9. Examples table and the cooking-oil decision
`python scripts/export_contract.py` then `python scripts/build_examples.py` writes `data/contract/examples.parquet` (+ `examples_stats.json`): one row per (article, product) with `text = title. summary. body[:1500]`, `realized_return = I(d+14)/I(d-1)-1`, `momentum_return = I(d-1)/I(d-15)-1`, exact-date endpoints only, at least 10 premises at each endpoint. No UP/DOWN/STABLE labels are produced. Product matching reuses the app repo's alias rules; the relevance audit (PRD M5) has not been done, so matches are noisy.

Cooking oil yields only 2 examples (its index has 306 usable days), so it is excluded from training (`--exclude-products cooking_oil`, default). Training covers rice, egg and chicken. Decision by ADIB on 2026-10-10 ("Keep 3"). Oil remains in the price files and index for context.
