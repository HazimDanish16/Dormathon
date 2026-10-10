# MyMarket data and Colab handoff, version 1

The teammate owns historical downloads, reviewed item mapping, price-index
construction, training, and evaluation in Google Colab. This repository owns
contracts, live ingestion, inference, and MCP serving. No training runs here.

## Data files

Put real files in `data/processed/`. Parquet string columns must contain strings,
required values cannot be null, and numerical columns must be finite. Additional
columns are allowed. `synthetic`, if supplied on real files, must be false.

| File | Required columns | Uniqueness |
|---|---|---|
| `news_clean.parquet` | `article_id`, `title`, `summary`, `body`, `source`, `url`, `language`, `published_at` | article ID and canonical URL |
| `price_index.parquet` | `product`, `date`, `index`, `n_premises` | product/date |
| `item_mapping.csv` | `product`, `item_code` | product/item code |
| `examples.parquet` | `article_id`, `product`, `domain`, `published_at`, `text`, `realized_return`, `momentum_return` | article/product |

IDs are strings. Product/domain keys must match `config/products.yaml`. URLs use
HTTP(S) without credentials. Publication timestamps include a timezone and are
normalized to UTC on load. Price dates are midnight timezone-free calendar dates
in Asia/Kuala_Lumpur. Index values are positive; premise counts are positive
integers; item codes are nonnegative integers. Review mappings manually.

Text is `title + '. ' + summary + '. ' + body[:1500]`. Returns are fractions,
not percentages. For article-local date d, realized return is `I(d+14)/I(d-1)-1`;
momentum return is `I(d-1)/I(d-15)-1`. Missing endpoints and insufficient premise
coverage must be excluded. News IDs in examples must exist in cleaned news;
price coverage must include examples' base and target dates.

Build prices as specified in PRD 6.4: clean outliers, normalize each item's
median over its first 90 days, average items, and apply seven-day smoothing.
Derive UP/DOWN/STABLE thresholds using training-period returns only. A label
column may be included for audit but is not an input to inference.

## Colab export interface

Export trusted teammate artifacts into `models/`. Joblib loading executes Python
serialization; never load files from an untrusted source. Include all five
artifact files, with SHA-256 hashes binding them to one export.

- `model.joblib`: a fitted, calibrated sklearn-compatible object with `classes_`
  and `predict_proba(DataFrame)`. The full preprocessing pipeline lives inside
  this object; it must be importable on the server without notebook-only classes.
- `label_map.json`: `{"classes": ["DOWN", "STABLE", "UP"]}` in the exact exported
  estimator probability order. All three classes must appear exactly once.
- `thresholds.json`: `{"horizon_days":14,"min_confidence":0.55,"products":{"rice":0.01,...}}`.
  Thresholds are nonnegative fractions derived from training data only.
- `metrics.json`: `schema_version=1`, `model_version`, `synthetic=false`,
  `dataset_provenance` (a nonempty object), `class_order` (same as label_map),
  `test` and `baselines`. Test fields:
  `macro_f1`, `macro_f1_ci95` (two numbers), `per_class` (precision/recall/F1/support
  per label), 3x3 `confusion_matrix` in class_order, `directional_accuracy`, `alert_precision`
  (null when undefined). Baselines contain majority, momentum, keyword objects
  with computed `macro_f1` values. Precision/recall/F1/support must agree with the
  confusion matrix; macro-F1 is the mean across all three labels, zero division=0.
  Include `rolling_origin`, optional `by_product`, and explicit `limitations`.
- `manifest.json`: `schema_version=1`, `model_version`, `synthetic=false`,
  `features=["text","product","domain"]`, `body_chars=1500`,
  `embedding_model="intfloat/multilingual-e5-small"`, immutable `embedding_revision`,
  `packages` (exact versions of numpy, pandas, scikit-learn, joblib and every
  serialization-critical package), `files` (SHA-256 for the four files above).

The app passes only text/product/domain to the fitted pipeline. TF-IDF and E5
pipelines share this interface. Embed with E5 `query: ` prefixes and normalize
vectors; use product one-hot and PRD event-word features inside the pipeline.
Package reusable custom transformers in `mymarket.model.features`, not `__main__`.
LightGBM models require installing the server's `training` dependency extra.

Chronological 70/15/15 split, 14-day purge, grouped duplicate events, validation
calibration, and validation-only model selection are mandatory. Report test
macro-F1, per-class results, confusion matrix, directional accuracy, alert
precision at probability >=0.7, bootstrapped 95% CI, quarterly rolling-origin
results, and majority/momentum/keyword baselines. Never claim uncomputed metrics.

## Fixtures and readiness

`scripts/generate_fixtures.py` creates deterministic FAKE data for app tests.
Fixture mode is explicit and uses named test doubles, not a trained model.
Every fixture dataset and response is marked synthetic. Real mode never falls
back to fake data. `scripts/validate_handoff.py` checks schemas, coverage, export
hashes, package compatibility, and an actual CPU probability prediction. Real
training and final accuracy validation remain the teammate's responsibility.
