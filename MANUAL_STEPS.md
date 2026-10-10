# MyMarket operator and teammate handoff

## Real data and model readiness

1. Give the teammate `DATA_AGENT_PROMPT.md`. They own preprocessing and Colab training.
2. Obtain the reviewed four-file data handoff and trusted five-file model export.
3. Place data in `data/processed/` and exports in `models/`, or configure their directories.
4. Match exported package versions and embedding revision. Run `uv sync --locked`
   with the optional `training` extra for LightGBM inference.
5. Run `uv run python scripts/cache_embeddings.py`, then
   `uv run python scripts/validate_handoff.py`. Resolve any reported mismatch.
6. Connect the client using README.md; call all eight tools with real inputs.
   Report only the supplied computed metrics and observed outcomes.

## News and explanations

Confirm feed URLs in a browser. FMT stays disabled until verified; add The Star
only after obtaining a working RSS URL. Templates need no API key. For a provider,
put its key and a supported model name in `.env`; never commit credentials.

## Relevance audit

1. Run `uv run python scripts/audit_relevance.py export --size 120`. It samples
   real cached alias matches, including those below the default threshold.
2. Open `data/audits/relevance.csv` in Excel or Sheets. Fill only `relevant`
   (`1` or `0`) and optional `notes`; keep all other cells and the JSON sidecar intact.
3. Label `1` for this product's price, supply, costs, subsidy, imports, shortages,
   or policy effects. Label `0` for recipes, restaurants, brands, incidental
   mentions, and stories about a different product. Read `text`, not just the title.
4. Run `uv run python scripts/audit_relevance.py assess`. It reports default
   precision, a tuning recommendation, held-out results, and uncertainty intervals.
5. Only when `ready_to_apply=true`, run the same command with `--apply`.
   It saves a provenance-bound threshold in `config/filter_threshold.json`.

Export refuses to overwrite existing labels. Use `--file data/audits/relevance_v2.csv`
for a fresh sample. A small cache exports fewer rows and remains provisional;
collect more real news before claiming a completed audit. Applying requires at
least 120 labeled real pairs and 20 accepted pairs in each partition with at least
80% observed precision, plus five accepted holdout pairs per configured product
with at least 80% precision. This is a point-estimate gate, not an 80% confidence bound.
The audit measures embedding filtering of alias candidates, not alias recall or
prediction accuracy. If exclusions change, export a fresh audit; runtime reverts
to untuned 0.80 when audited configuration or embedding provenance is stale.

## Scheduling

Preview polling with `scripts/install_schedule.ps1 -Task Poll`; add `-Apply` to
register it. Obtain the teammate's price-refresh command and configure its JSON
argument list. Run daily refresh manually, inspect `data/refresh/latest.json`,
and resolve any `incomplete` status. Only then register `-Task Daily -Apply`.
Daily execution is at 14:00 with the computer timezone set to Asia/Kuala_Lumpur.
Verify Task Scheduler's Last Run Result; overlapping executions are disabled.
