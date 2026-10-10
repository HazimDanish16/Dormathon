# Repository Guidelines

## Project Structure & Module Organization

HargaRadar is a planned Python 3.11 backend-only MCP server for Malaysian news and product-price awareness. Currently, this workspace contains `PRD.md` and `APP_AGENT_PROMPT.md` only. Read both before implementation; their phase instructions do not authorize work beyond the current task.

Follow the planned layout: `src/harga/` for ingestion, relevance filtering, price context, prediction, explanations, storage, and `mcp_server.py`; `config/` for product mappings and feeds; `scripts/` for offline pipelines and refresh jobs; `notebooks/` for Colab training; and `tests/fixtures/` for clearly named `FAKE` datasets. Keep raw downloads in `data/raw/`, processed inputs in `data/processed/`, and model artifacts alongside `metrics.json` in `models/`. Ignore large datasets and runtime caches.

## Build, Test, and Development Commands

These commands apply once the scaffold and dependencies exist; they are not currently runnable end to end:

- `uv venv`: create the local environment; activate with `.venv\Scripts\Activate.ps1` on Windows.
- `uv pip install -r requirements.txt`: install project dependencies.
- `uv run pytest`: run the test suite.
- `uv run python -m harga.mcp_server`: start the MCP server, once `harga` is importable from `src/`.
- `npx @modelcontextprotocol/inspector uv run python -m harga.mcp_server`: inspect and exercise MCP tools.

## Coding Style & Naming Conventions

Use four-space indentation, `snake_case` modules and functions, `PascalCase` classes, and descriptive product keys such as `cooking_oil`. Keep products and feeds configuration-driven. No formatter or linter is configured yet. Send MCP logs to stderr and return structured JSON errors with `error` and `hint` fields.

## Testing Guidelines

Use pytest with `test_*.py` files. Cover alias exclusions, price-index calculations, label construction, schema validation, and MCP error responses. Keep fake fixtures separate from real inputs. No numeric coverage target is specified. Evaluate models using chronological splits with a 14-day purge; report macro-F1 and majority, momentum, and keyword baselines.

## Commit & Pull Request Guidelines

No Git history is available to establish conventions. Prefer concise imperative commits, such as `Add RSS ingestion cache`. PRs should explain behavior, link relevant requirements or issues, and report validation results. Label fixture metrics as fake.

## Security & Data Boundaries

Keep secrets in `.env`; provide `.env.example`. Respect robots.txt, use plain Scrapling `Fetcher`, and limit requests to one per second per host. MCP must consume processed price indexes. Obtain missing data-contract schemas before creating fixtures; do not invent them.
