# MyMarket MCP

Backend-only MCP server for Malaysian news and product-price awareness.
The stdio server exposes all eight planned tools. `list_domains` reads
the product configuration and `fetch_news` queries the SQLite news cache.
The other six return explicit JSON errors until
their pipelines are implemented. There are no real predictions or metrics yet.

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
Install optional LightGBM training support with `uv sync --locked --extra training`.
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
if configuration is invalid. Tool responses use JSON; pending pipeline tools
return `{"error": "...", "hint": "..."}`.

## Configuration and structure

- `config/products.yaml`: English/Malay aliases, exclusion phrases, and reviewed
  item codes for rice, egg, cooking oil, and chicken. Item mappings are empty
  pending data-team review. Consumer products are not selected yet.
- `config/sources.yaml`: Malay Mail and Bernama enabled from the PRD; FMT disabled
  pending verification. Feed availability has not been tested by this scaffold.
- `.env`: optional `MYMARKET_CONFIG_DIR` and `MYMARKET_LOG_LEVEL` overrides; environment
  variables take precedence. Relative config paths resolve from the project root.
- `MYMARKET_DATABASE_PATH`: SQLite location, defaulting to `data/mymarket.sqlite3`.
  Relative database paths also resolve from the project root. Runtime databases are ignored by Git.
- `src/mymarket/`: entry point and config loader, with packages reserved for ingestion,
  filtering, prices, models, explanations, and SQLite storage.
- `tests/`: configuration, ingestion, cache, and subprocess MCP stdio tests.

Development installs are editable. If installing a wheel elsewhere, set
`MYMARKET_PROJECT_ROOT` to a directory containing `config/` and optional `.env`.
The missing `DATA_AGENT_PROMPT.md` contract is required before creating data
fixtures. No historical data or model weights are downloaded by the scaffold.

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
