# MyMarket MCP

Backend-only MCP server for Malaysian news and product-price awareness.
The stdio server scaffold exposes all eight planned tools. `list_domains` reads
the product configuration; the other seven return explicit JSON errors until
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
- `src/mymarket/`: entry point and config loader, with packages reserved for ingestion,
  filtering, prices, models, explanations, and SQLite storage.
- `tests/`: YAML validation and a real subprocess MCP stdio test.

Development installs are editable. If installing a wheel elsewhere, set
`MYMARKET_PROJECT_ROOT` to a directory containing `config/` and optional `.env`.
The missing `DATA_AGENT_PROMPT.md` contract is required before creating data
fixtures. No historical data or model weights are downloaded by the scaffold.
