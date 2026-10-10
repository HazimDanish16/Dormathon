# MyMarket MCP

Backend-only MCP server for Malaysian news and product-price awareness.
All eight MCP tools are implemented. Live news ingestion works independently;
real predictions require the teammate's processed data and Google Colab model
exports. No training runs in this repository and no real model accuracy is
claimed before the handoff. Fixture demonstrations use named test doubles and
mark every response as synthetic.

## Development setup

Use Python 3.11 and [uv](https://docs.astral.sh/uv/getting-started/installation/).
From the repository root:

```powershell
uv sync --locked
Copy-Item .env.example .env
```

`uv sync` creates `.venv`, installs Python if needed, and includes pytest.
On this workstation, a local uv executable is available at `.tools/uv/uv.exe`;
use `& .\.tools\uv\uv.exe sync --locked` if `uv` is not on PATH.

Dependencies cover the official MCP SDK, RSS ingestion, article fetching,
Parquet price data, CPU model inference, and Gemini explanations. SQLite is
provided by Python. PyTorch uses its CPU index on Windows and Linux.
Install optional LightGBM inference support with `uv sync --locked --extra training`.
Scrapling browser binaries and embedding model weights are not downloaded
during setup. Article fetching must use plain `Fetcher` and respect robots.txt.

## Dependency maintenance

`pyproject.toml` declares dependencies; `uv.lock` records exact resolved versions.
After changing dependencies, run `uv lock`, then `uv sync --locked`.
Regenerate the compatibility requirements file with:

```powershell
uv export --locked --no-hashes --no-emit-project --emit-index-url --output-file requirements.txt
```

Prefer `uv sync --locked` for development. The exported requirements file includes
development dependencies; LightGBM remains an optional extra.
See `PRD.md`, `APP_AGENT_PROMPT.md`, and `AGENTS.md` for implementation scope
and contributor guidance.

## Run and inspect

```powershell
uv run python -m mymarket.mcp_server
# Equivalent installed entry point:
uv run mymarket
# Connect with MCP Inspector (requires Node.js):
npx @modelcontextprotocol/inspector uv run python -m mymarket.mcp_server
# Configuration and stdio integration tests:
uv run pytest
```

The server waits for MCP messages on stdin. Logs go to stderr; stdout is reserved
for protocol messages. Startup validates both YAML files and exits with code 2
if configuration is invalid. Tool responses use JSON; invalid requests and missing
handoff inputs return `{"error": "...", "hint": "..."}`.

## Configuration and structure

- `config/products.yaml`: English/Malay aliases, exclusion phrases, and reviewed
  item codes for rice, egg, cooking oil, and chicken. Item mappings are empty
  pending data-team review. Consumer products are not selected yet.
- `config/sources.yaml`: Malay Mail and Bernama verified during development; FMT
  disabled pending verification.
- `.env`: optional `MYMARKET_CONFIG_DIR` and `MYMARKET_LOG_LEVEL` overrides; environment
  variables take precedence. Relative config paths resolve from the project root.
- `MYMARKET_DATABASE_PATH`: SQLite location, defaulting to `data/mymarket.sqlite3`.
  Relative database paths also resolve from the project root. Runtime databases are ignored by Git.
- `src/mymarket/`: entry point and config loader, with packages for ingestion,
  filtering, prices, models, explanations, and SQLite storage.
- `tests/`: configuration, ingestion, cache, and subprocess MCP stdio tests.

Development installs are editable. If installing a wheel elsewhere, set
`MYMARKET_PROJECT_ROOT` to a directory containing `config/` and optional `.env`.
See `DATA_AGENT_PROMPT.md` for the versioned data and model contracts. Missing or
incompatible inputs return actionable errors. Real mode never substitutes fake data.

## Poll and query news

```powershell
uv run python scripts/poll_news.py
```

This standalone command prints a JSON report with status, item count, inserted
articles, duplicates, skipped entries, and newest publication date per source.
One failing source does not stop the others. Exit code 1 means startup failed,
all enabled sources failed, or no sources were enabled. A partial success exits 0;
check the report for individual source failures.

Schedule this command every few hours from the repository directory using
Windows Task Scheduler or cron. Do not overlap polling jobs. RSS feeds contain
only recent entries, so regular polling is needed to build history.

The poller respects robots.txt and waits at least one second between requests to
the same host, honoring longer crawl delays. It skips article fetching when RSS
already contains sufficient text and a publication date. Plain Scrapling
`Fetcher` uses no browser impersonation or stealth headers. Blocked, short,
paywalled, or failed article responses fall back to RSS text. Missing publication
dates are extracted from article metadata when possible; otherwise fetch time is
stored with `date_estimated=true`. Both the article body and its provenance are cached.

Call `fetch_news` through Inspector with, for example:

```json
{"hours": 48, "sources": ["malay_mail", "bernama"], "limit": 20}
```

It returns only cached articles, with publication timestamps in Asia/Kuala_Lumpur.
An empty cache returns an empty article list. Use source IDs from `sources.yaml`;
unknown IDs and invalid query ranges return JSON errors.

Malay Mail and Bernama passed a live polling check during development. Confirm
the URLs in a browser before scheduling; enable FMT only after it works, and add
The Star only after copying a valid RSS URL from its RSS page.

## Teammate handoff and real readiness

1. Obtain the four processed files defined in `DATA_AGENT_PROMPT.md`; place them in
   `data/processed/`. Item mapping must cover all products and be reviewed by your teammate.
2. Put the five trusted Colab exports in `models/`: model, label map, thresholds,
   metrics, and manifest. Install matching serialization-critical package versions;
   include `--extra training` if the pipeline uses LightGBM. Joblib is executable
   serialization, so use only your teammate's trusted exports.
3. Align `MYMARKET_EMBEDDING_REVISION` with the manifest, then run:

```powershell
uv run python scripts/cache_embeddings.py
uv run python scripts/validate_handoff.py
```

The first command downloads pinned E5 weights and checks CPU inference; it does
not train the price model. Runtime embedding calls use cached files only. The
second validates schemas, cross-file dates/IDs, return calculations, export
hashes, package versions, metric consistency, and an actual prediction. It exits
1 on an incomplete or incompatible handoff. Retain the supplied provenance.

`predict_impact` accepts text or a cached article URL. All computed predictions
are logged. Text-only requests have unverified publication dates and are excluded
from forward scoring and cached-news queries. `price_context` returns null changes
and warnings for missing exact comparison dates. `backtest_report` reads supplied
metrics; it never estimates missing product results.

`scan_alerts` processes up to 100 article/product matches, records abstentions,
and uses an elapsed-time budget for embeddings and explanations. Cold CPU loads
or a slow exported pipeline may exceed the 60-second target; prewarm the encoder
and verify real-data latency after handoff. No latency measurement from fixtures
is claimed as real-model performance.

## Relevance audit

For human relevance review, run `uv run python scripts/audit_relevance.py export`.
Label the CSV's `relevant` column, then run the command with `assess`.
See `MANUAL_STEPS.md` for labeling rules and held-out threshold validation.
The default 0.80 remains untuned until a sufficient real audit is applied.

## Explanations

Without provider credentials or a model name, English/Malay templates work
automatically. Configure `LLM_PROVIDER=gemini`, `groq`, or `ollama`, a current
`LLM_MODEL`, and the corresponding key or local Ollama URL to enable JSON provider
explanations. They receive only computed facts and article metadata. Schema,
product/direction, numeric, vocabulary, and disclaimer checks guard the result;
one failed retry falls back to a template. Fixture mode always uses templates.

## Synthetic demo and offline checks

```powershell
uv run python scripts/demo.py
uv run pytest -q
```

The demo generates 200 fake news rows, two years of four-product prices, and 500
fake examples in ignored `.tools/FAKE-demo/`, then seeds a separate FAKE database.
The fixture predictor emits fixed test probabilities, not a trained forecast.
No backtest accuracy is fabricated. Tests exercise every tool over real stdio
with fake inputs; ordinary tests require no API keys, downloads, or live feeds.
GitHub Actions runs the same offline suite on each push and pull request.

For a fixture MCP client set `MYMARKET_DATA_MODE=fixture`, `MYMARKET_DATA_DIR` to
the demo folder, and `MYMARKET_DATABASE_PATH` to its `FAKE.sqlite3`. Fixture database
names must start with FAKE. Keep the live and fixture configurations separate.

## Daily refresh and scheduling

```powershell
uv run python scripts/daily_refresh.py
.\scripts\install_schedule.ps1 -Task Poll
.\scripts\install_schedule.ps1 -Task Poll -Apply
```

Daily refresh delegates price preprocessing to your teammate's command, configured
as a JSON argument list in `MYMARKET_PRICE_REFRESH_COMMAND`, for example
`["C:/path/to/python.exe","C:/data-team/refresh_prices.py"]`. It invokes that command
without a shell from the project directory, with a ten-minute timeout. The data
team must update the processed price index atomically. No raw prices are read by MCP.

The job polls news, validates the handoff, scans alerts, and scores matured outcomes.
Missing data or an unconfigured/failed price refresh produces `status=incomplete`
and exit code 1. Its latest report is saved to ignored `data/refresh/latest.json`.
Forward validation excludes estimated dates, retrospective predictions, and
abstentions. Scoring uses the saved threshold and exact base/target dates, once
per outcome; reports retain per-model breakdowns.

The schedule script previews by default. `-Apply` registers an idempotent task
with overlapping runs disabled. Polling runs every three hours. After the real
handoff and price command are ready, use `-Task Daily -Apply` for 14:00 daily;
configure the computer timezone as Asia/Kuala_Lumpur. Inspect Task Scheduler's
Last Run Result and the refresh report. Daily scheduling is deliberately gated
by a successful real handoff check. Linux equivalents: polling `0 */3 * * *`
and daily refresh `0 14 * * *`, with cron timezone Asia/Kuala_Lumpur and absolute
Python/script paths.

## MCP client connection

For Claude Desktop, add this server entry using your absolute project path:

```json
{"mcpServers":{"mymarket":{"command":"uv","args":["--directory","C:/path/to/Dormathon","run","--locked","mymarket"]}}}
```

If uv is not on PATH, use the absolute `.tools/uv/uv.exe` path as `command`.
Restart the client, list domains, fetch news, then inspect price context and alerts.
The PRD's demo flow also includes backtest reporting and forward validation.

PriceCatcher is price-surveillance data, not an official inflation index. News
signals are weak; explanations are awareness only, not financial advice. Review
the PRD's F1-F13 limitations and report model failures and baseline comparisons
honestly. Fuel, consumer-product selection, UI, and model training are outside
this app track.
