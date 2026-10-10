# Repository Guidelines

## Project Structure & Module Organization

MyMarket is a Python 3.11 backend-only MCP server for Malaysian news and product-price awareness. The stdio scaffold and configuration exist; only `list_domains` is implemented. Read `PRD.md` and `APP_AGENT_PROMPT.md` before implementation; their phase instructions do not authorize work beyond the current task.

Follow the planned layout: `src/mymarket/` for ingestion, relevance filtering, price context, prediction, explanations, storage, and `mcp_server.py`; `config/` for product mappings and feeds; `scripts/` for offline pipelines and refresh jobs; `notebooks/` for Colab training; and `tests/fixtures/` for clearly named `FAKE` datasets. Keep raw downloads in `data/raw/`, processed inputs in `data/processed/`, and model artifacts alongside `metrics.json` in `models/`. Ignore large datasets and runtime caches.

## Build, Test, and Development Commands

Use `pyproject.toml` for dependency declarations and `uv.lock` for reproducible installs. A local Windows uv executable is available at `.tools/uv/uv.exe` if uv is not on PATH.

- `uv sync --locked`: create `.venv` and install runtime and development dependencies.
- `uv sync --locked --extra training`: include optional LightGBM.
- `uv run pytest`: run configuration and stdio integration tests.
- `uv run python -m mymarket.mcp_server`: start the stdio MCP server.
- `npx @modelcontextprotocol/inspector uv run python -m mymarket.mcp_server`: inspect and exercise MCP tools.

## Coding Style & Naming Conventions

Use four-space indentation, `snake_case` modules and functions, `PascalCase` classes, and descriptive product keys such as `cooking_oil`. Keep products and feeds configuration-driven. No formatter or linter is configured yet. Send MCP logs to stderr and return structured JSON errors with `error` and `hint` fields.

## Testing Guidelines

Use pytest with `test_*.py` files. Cover alias exclusions, price-index calculations, label construction, schema validation, and MCP error responses. Keep fake fixtures separate from real inputs. No numeric coverage target is specified. Evaluate models using chronological splits with a 14-day purge; report macro-F1 and majority, momentum, and keyword baselines.

## Commit & Pull Request Guidelines

The initial commit uses a concise imperative subject. Follow that style, such as `Add RSS ingestion cache`. PRs should explain behavior, link relevant requirements or issues, and report validation results. Label fixture metrics as fake.

## Security & Data Boundaries

Keep secrets in `.env`; provide `.env.example`. Respect robots.txt, use plain Scrapling `Fetcher`, and limit requests to one per second per host. MCP must consume processed price indexes. Obtain missing data-contract schemas before creating fixtures; do not invent them.
