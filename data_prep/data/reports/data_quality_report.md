# Data quality report
## 1. Source files
- Months downloaded OK (from download log): ['2023-07', '2023-08', '2023-09', '2023-10', '2023-11', '2023-12', '2024-01', '2024-02', '2024-03', '2024-04', '2024-05', '2024-06', '2024-07', '2024-08', '2024-09', '2024-10', '2024-11', '2024-12', '2025-01', '2025-02', '2025-03', '2025-04', '2025-05', '2025-06', '2025-07', '2025-08', '2025-09', '2025-10', '2025-11', '2025-12', '2026-01', '2026-02', '2026-03', '2026-04', '2026-05', '2026-06', '2026-07', '2026-08', '2026-09']
- Months unavailable (404): ['2026-10']
- **skipped_existing**: []
- **unavailable_404**: ['2026-10']
- **failed**: {}
- **rows_kept**: 11818871
- **source_files_ok**: 39
- **pattern**: https://storage.data.gov.my/pricecatcher/pricecatcher_YYYY-MM.parquet
## 2. Date coverage
- Prices (daily item table): 2023-07-01 to 2026-09-24
- News: 2020-10-31 to 2026-10-09 (date_only timestamps)
## 3. Price cleaning (rows before and after)
- rows_input: 7178345
- rows_rejected_total: 0
- rows_after_cleaning: 7178345
- outliers_flagged: 593
- rows_valid_for_stats: 7177752
- rows_without_baseline: 39759
- exact_duplicates_dropped: 0
- key_conflict_rows_rejected: 0
- rejected by reason: {}
- missing values in input: {'date': 0, 'premise_code': 0, 'item_code': 0, 'price': 0}
## 4. Valid observations by product
- chicken: 1060845 observations over 2221 item-days (2023-07-01 to 2026-09-24)
- cooking_oil: 3563585 observations over 12086 item-days (2023-07-01 to 2026-09-21)
- egg: 1671076 observations over 5501 item-days (2023-07-01 to 2026-09-24)
- rice: 882246 observations over 7523 item-days (2023-07-03 to 2026-09-23)
## 5. Coverage by month (index days / median items / median premises)

**chicken**

| month | days | median items | median premises |
|---|---|---|---|
| 2023-07 | 30 | 0.0 | 787.5 |
| 2023-08 | 29 | 0.0 | 788.0 |
| 2023-09 | 28 | 0.0 | 790.0 |
| 2023-10 | 30 | 2.0 | 797.5 |
| 2023-11 | 28 | 2.0 | 802.5 |
| 2023-12 | 24 | 2.0 | 796.5 |
| 2024-01 | 31 | 2.0 | 804.0 |
| 2024-02 | 27 | 2.0 | 819.0 |
| 2024-03 | 28 | 2.0 | 829.0 |
| 2024-04 | 28 | 2.0 | 833.0 |
| 2024-05 | 30 | 2.0 | 845.0 |
| 2024-06 | 28 | 2.0 | 844.0 |
| 2024-07 | 30 | 2.0 | 856.0 |
| 2024-08 | 26 | 2.0 | 862.5 |
| 2024-09 | 29 | 2.0 | 864.0 |
| 2024-10 | 31 | 2.0 | 862.0 |
| 2024-11 | 28 | 2.0 | 861.0 |
| 2024-12 | 30 | 2.0 | 870.5 |
| 2025-01 | 29 | 2.0 | 868.0 |
| 2025-02 | 26 | 2.0 | 871.0 |
| 2025-03 | 30 | 2.0 | 884.0 |
| 2025-04 | 28 | 2.0 | 880.5 |
| 2025-05 | 29 | 2.0 | 890.0 |
| 2025-06 | 27 | 2.0 | 889.0 |
| 2025-07 | 30 | 2.0 | 927.0 |
| 2025-08 | 30 | 2.0 | 1030.5 |
| 2025-09 | 28 | 2.0 | 1023.0 |
| 2025-10 | 31 | 2.0 | 1028.0 |
| 2025-11 | 30 | 2.0 | 1026.0 |
| 2025-12 | 30 | 2.0 | 1027.0 |
| 2026-01 | 31 | 2.0 | 1020.0 |
| 2026-02 | 25 | 2.0 | 1014.0 |
| 2026-03 | 25 | 2.0 | 1014.0 |
| 2026-04 | 30 | 2.0 | 1018.0 |
| 2026-05 | 29 | 2.0 | 1019.0 |
| 2026-06 | 27 | 2.0 | 1015.0 |
| 2026-07 | 31 | 2.0 | 1017.0 |
| 2026-08 | 29 | 2.0 | 1016.0 |
| 2026-09 | 23 | 2.0 | 1024.0 |

**cooking_oil**

| month | days | median items | median premises |
|---|---|---|---|
| 2023-07 | 30 | 0.0 | 608.0 |
| 2023-08 | 29 | 0.0 | 608.0 |
| 2023-09 | 27 | 0.0 | 602.0 |
| 2023-10 | 30 | 27.0 | 605.5 |
| 2023-11 | 28 | 27.0 | 602.0 |
| 2023-12 | 24 | 27.0 | 602.5 |
| 2024-01 | 31 | 27.0 | 602.0 |
| 2024-02 | 20 | 22.0 | 6.5 |
| 2024-03 | 19 | 20.0 | 3.0 |
| 2024-04 | 16 | 18.0 | 6.0 |
| 2024-05 | 20 | 17.0 | 5.5 |
| 2024-06 | 11 | 20.0 | 8.0 |
| 2024-07 | 13 | 22.0 | 11.0 |
| 2024-08 | 11 | 16.0 | 9.0 |
| 2024-09 | 15 | 16.0 | 9.0 |
| 2024-10 | 12 | 17.5 | 7.5 |
| 2024-11 | 9 | 16.0 | 8.0 |
| 2024-12 | 16 | 15.0 | 8.0 |
| 2025-01 | 13 | 27.0 | 154.0 |
| 2025-02 | 11 | 16.0 | 9.0 |
| 2025-03 | 12 | 18.5 | 73.5 |
| 2025-04 | 10 | 19.5 | 76.5 |
| 2025-05 | 9 | 27.0 | 1217.0 |
| 2025-06 | 9 | 21.0 | 209.0 |
| 2025-07 | 9 | 21.0 | 82.0 |
| 2025-08 | 12 | 19.0 | 29.0 |
| 2025-09 | 8 | 21.0 | 864.5 |
| 2025-10 | 8 | 20.0 | 880.5 |
| 2025-11 | 10 | 17.5 | 9.0 |
| 2025-12 | 11 | 19.0 | 8.0 |
| 2026-01 | 11 | 17.0 | 10.0 |
| 2026-02 | 6 | 18.0 | 854.5 |
| 2026-03 | 10 | 21.0 | 203.5 |
| 2026-04 | 8 | 19.0 | 841.0 |
| 2026-05 | 12 | 19.0 | 106.0 |
| 2026-06 | 10 | 19.5 | 714.0 |
| 2026-07 | 9 | 19.0 | 177.0 |
| 2026-08 | 11 | 19.0 | 51.0 |
| 2026-09 | 6 | 20.0 | 870.0 |

**egg**

| month | days | median items | median premises |
|---|---|---|---|
| 2023-07 | 30 | 0.0 | 433.5 |
| 2023-08 | 29 | 0.0 | 386.0 |
| 2023-09 | 27 | 0.0 | 322.0 |
| 2023-10 | 30 | 6.0 | 324.5 |
| 2023-11 | 28 | 6.0 | 358.5 |
| 2023-12 | 24 | 6.0 | 385.5 |
| 2024-01 | 31 | 6.0 | 403.0 |
| 2024-02 | 27 | 6.0 | 411.0 |
| 2024-03 | 28 | 6.0 | 494.5 |
| 2024-04 | 28 | 6.0 | 574.5 |
| 2024-05 | 29 | 6.0 | 599.0 |
| 2024-06 | 28 | 6.0 | 488.0 |
| 2024-07 | 30 | 6.0 | 482.5 |
| 2024-08 | 25 | 6.0 | 488.0 |
| 2024-09 | 29 | 6.0 | 469.0 |
| 2024-10 | 31 | 6.0 | 507.0 |
| 2024-11 | 28 | 6.0 | 542.5 |
| 2024-12 | 30 | 6.0 | 576.0 |
| 2025-01 | 29 | 6.0 | 616.0 |
| 2025-02 | 26 | 6.0 | 636.5 |
| 2025-03 | 30 | 6.0 | 661.0 |
| 2025-04 | 28 | 6.0 | 643.5 |
| 2025-05 | 29 | 6.0 | 671.0 |
| 2025-06 | 26 | 6.0 | 673.5 |
| 2025-07 | 30 | 6.0 | 696.5 |
| 2025-08 | 30 | 3.0 | 779.0 |
| 2025-09 | 27 | 3.0 | 752.0 |
| 2025-10 | 31 | 3.0 | 803.0 |
| 2025-11 | 30 | 3.0 | 815.0 |
| 2025-12 | 30 | 3.0 | 820.0 |
| 2026-01 | 31 | 3.0 | 853.0 |
| 2026-02 | 25 | 3.0 | 821.0 |
| 2026-03 | 25 | 3.0 | 846.0 |
| 2026-04 | 30 | 3.0 | 880.5 |
| 2026-05 | 29 | 3.0 | 873.0 |
| 2026-06 | 27 | 3.0 | 882.0 |
| 2026-07 | 31 | 3.0 | 883.0 |
| 2026-08 | 29 | 3.0 | 860.0 |
| 2026-09 | 23 | 3.0 | 851.0 |

**rice**

| month | days | median items | median premises |
|---|---|---|---|
| 2023-07 | 13 | 0.0 | 1.0 |
| 2023-08 | 11 | 0.0 | 2.0 |
| 2023-09 | 19 | 0.0 | 286.0 |
| 2023-10 | 30 | 14.0 | 374.5 |
| 2023-11 | 28 | 15.0 | 379.5 |
| 2023-12 | 24 | 14.0 | 375.0 |
| 2024-01 | 20 | 2.0 | 1.5 |
| 2024-02 | 10 | 4.0 | 13.0 |
| 2024-03 | 7 | 13.0 | 513.0 |
| 2024-04 | 28 | 6.0 | 557.0 |
| 2024-05 | 30 | 6.0 | 573.0 |
| 2024-06 | 28 | 6.0 | 567.5 |
| 2024-07 | 30 | 8.0 | 592.0 |
| 2024-08 | 26 | 8.0 | 591.0 |
| 2024-09 | 29 | 8.0 | 591.0 |
| 2024-10 | 31 | 8.0 | 585.0 |
| 2024-11 | 28 | 8.0 | 591.0 |
| 2024-12 | 30 | 8.0 | 589.5 |
| 2025-01 | 29 | 8.0 | 598.0 |
| 2025-02 | 26 | 8.0 | 595.0 |
| 2025-03 | 30 | 8.0 | 612.0 |
| 2025-04 | 28 | 8.0 | 590.5 |
| 2025-05 | 29 | 8.0 | 603.0 |
| 2025-06 | 26 | 8.0 | 598.0 |
| 2025-07 | 30 | 8.0 | 607.5 |
| 2025-08 | 26 | 5.0 | 4.0 |
| 2025-09 | 18 | 3.0 | 2.0 |
| 2025-10 | 21 | 2.0 | 1.0 |
| 2025-11 | 19 | 3.0 | 1.0 |
| 2025-12 | 19 | 4.0 | 1.0 |
| 2026-01 | 19 | 4.0 | 1.0 |
| 2026-02 | 13 | 3.0 | 1.0 |
| 2026-03 | 16 | 4.0 | 1.0 |
| 2026-04 | 15 | 4.0 | 1.0 |
| 2026-05 | 18 | 3.0 | 2.0 |
| 2026-06 | 13 | 3.0 | 1.0 |
| 2026-07 | 17 | 4.0 | 1.0 |
| 2026-08 | 12 | 5.0 | 44.0 |
| 2026-09 | 15 | 2.0 | 1.0 |

## 6. Missing price days (index)
- chicken: 69 missing day(s): 2023-07-19, 2023-08-30, 2023-08-31, 2023-09-09, 2023-09-16, 2023-10-21, 2023-11-28, 2023-11-29, 2023-12-08, 2023-12-09, 2023-12-10, 2023-12-13, 2023-12-14, 2023-12-15, 2023-12-25, 2024-02-10, 2024-02-11, 2024-03-01, 2024-03-02, 2024-03-03, 2024-04-10, 2024-04-11, 2024-05-01, 2024-06-03, 2024-06-17, 2024-07-21, 2024-08-07, 2024-08-23, 2024-08-24, 2024-08-25 ...
- cooking_oil: 613 missing day(s): 2023-07-19, 2023-08-30, 2023-08-31, 2023-09-09, 2023-09-16, 2023-09-28, 2023-10-21, 2023-11-28, 2023-11-29, 2023-12-08, 2023-12-09, 2023-12-10, 2023-12-13, 2023-12-14, 2023-12-15, 2023-12-25, 2024-02-02, 2024-02-09, 2024-02-10, 2024-02-11, 2024-02-12, 2024-02-20, 2024-02-21, 2024-02-24, 2024-02-27, 2024-03-01, 2024-03-02, 2024-03-03, 2024-03-05, 2024-03-07 ...
- egg: 74 missing day(s): 2023-07-19, 2023-08-30, 2023-08-31, 2023-09-09, 2023-09-16, 2023-09-28, 2023-10-21, 2023-11-28, 2023-11-29, 2023-12-08, 2023-12-09, 2023-12-10, 2023-12-13, 2023-12-14, 2023-12-15, 2023-12-25, 2024-02-10, 2024-02-11, 2024-03-01, 2024-03-02, 2024-03-03, 2024-04-10, 2024-04-11, 2024-05-01, 2024-05-22, 2024-06-03, 2024-06-17, 2024-07-21, 2024-08-07, 2024-08-23 ...
- rice: 318 missing day(s): 2023-07-05, 2023-07-07, 2023-07-08, 2023-07-09, 2023-07-13, 2023-07-14, 2023-07-15, 2023-07-16, 2023-07-19, 2023-07-20, 2023-07-21, 2023-07-22, 2023-07-23, 2023-07-28, 2023-07-29, 2023-07-30, 2023-08-02, 2023-08-03, 2023-08-04, 2023-08-05, 2023-08-06, 2023-08-08, 2023-08-09, 2023-08-10, 2023-08-11, 2023-08-12, 2023-08-16, 2023-08-18, 2023-08-19, 2023-08-22 ...
## 7. News cleaning
- rows read 154445, kept 153653, rejected 792
- rejected by reason: {'near_duplicate_title': 446, 'duplicate_url': 344, 'unusable_date': 2}
- articles per year: {'2020': 1, '2023': 79, '2024': 50643, '2025': 56523, '2026': 46407}
- dedup rules: normalised URL; content_id; normalised title within +-1 day (first occurrence kept)
## 8. Known limitations and unresolved ambiguities
- News `published_date` has no time of day (date only); same-day publication order is unknown.
- PriceCatcher is a survey of premises, not a census; coverage varies by day and premise.
- Product indexes mix brands and pack sizes by normalising each item to its own reference median.
- Items without enough reference-window data are excluded from the raw index (listed in index_item_baselines.csv).
- Mapping review item 3 (AYAM HIDUP): suggested `no`: Live chicken priced per kg live weight, a different basis from dressed chicken; suggest excluding.
- Mapping review item 1364 (AYAM TUA HIDUP): suggested `no`: Old hen sold live: different basis (live weight) and bird type; suggest excluding.
- Mapping review item 918 (MINYAK MASAK PAKET (PELBAGAI JENAMA)): suggested `no`: 1kg 'paket' oil, assumed to be the government-subsidised packet (inferred from the name; the lookup does not say). Subsidised and unsubsidised oil must not be mixed without approval; suggest excluding from the main index.
- Mapping review item 1930 (TELUR AYAM KAMPUNG): suggested `no`: Free-range (kampung) hen egg: different product and price level; suggest excluding.
- Mapping review item 992 (BERAS CAP JATI (SST5%)): suggested `yes`: White rice; the lookup does not say whether it is local or imported (SST5% / Sabah brands) or confirm the grade. Mixing origins and grades needs a human decision.
- Mapping review item 1445 (BERAS CAP FAIZA EMAS (SST5%)): suggested `yes`: White rice; the lookup does not say whether it is local or imported (SST5% / Sabah brands) or confirm the grade. Mixing origins and grades needs a human decision.
- Mapping review item 1581 (BERAS CAP RAMBUTAN (SST5%)): suggested `yes`: White rice; the lookup does not say whether it is local or imported (SST5% / Sabah brands) or confirm the grade. Mixing origins and grades needs a human decision.
- Mapping review item 1582 (BERAS CAP JASMINE (SST5%)): suggested `yes`: White rice; the lookup does not say whether it is local or imported (SST5% / Sabah brands) or confirm the grade. Mixing origins and grades needs a human decision.
- Mapping review item 1823 (BERAS TKC SABAH CAP TQR 5%): suggested `yes`: White rice; the lookup does not say whether it is local or imported (SST5% / Sabah brands) or confirm the grade. Mixing origins and grades needs a human decision.
- Mapping review item 1824 (BERAS TKC SUPER HUMA CAP KELISA EMAS (SABAH)): suggested `yes`: White rice; the lookup does not say whether it is local or imported (SST5% / Sabah brands) or confirm the grade. Mixing origins and grades needs a human decision.

## 9. Validation

41/41 checks passed.
