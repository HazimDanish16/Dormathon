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

## Scheduling

Preview polling with `scripts/install_schedule.ps1 -Task Poll`; add `-Apply` to
register it. Obtain the teammate's price-refresh command and configure its JSON
argument list. Run daily refresh manually, inspect `data/refresh/latest.json`,
and resolve any `incomplete` status. Only then register `-Task Daily -Apply`.
Daily execution is at 14:00 with the computer timezone set to Asia/Kuala_Lumpur.
Verify Task Scheduler's Last Run Result; overlapping executions are disabled.
