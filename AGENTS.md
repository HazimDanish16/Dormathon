# Repository Guidelines

## Project Structure & Module Organization

MyMarket is a Python 3.11 MCP server for Malaysian news and product-price awareness. Real predictions require teammate data and Colab exports. Read `PRD.md`, `APP_AGENT_PROMPT.md`, and `DATA_AGENT_PROMPT.md` before implementation.

Use `src/mymarket/` for ingestion, filtering, prices, inference, explanations, and storage; `config/` for products and feeds; `scripts/` for validation, demonstrations, and refresh orchestration; and `tests/` for offline checks. Teammates own historical preprocessing and Colab training. Real processed inputs belong in `data/processed/`, trusted exports in `models/`, and generated FAKE fixtures in ignored `.tools/` folders.

## Build, Test, and Development Commands

Declare dependencies in `pyproject.toml`; lock installs with `uv.lock`. Windows uv is available at `.tools/uv/uv.exe`.

- `uv sync --locked`: create `.venv` and install runtime and development dependencies.
- `uv sync --locked --extra training`: include optional LightGBM.
- `uv run pytest`: run configuration and stdio integration tests.
- `uv run python scripts/poll_news.py`: poll feeds and populate the SQLite cache.
- `uv run python scripts/validate_handoff.py`: validate teammate data and exports.
- `uv run python scripts/demo.py`: demonstrate synthetic app behavior without training.
- `uv run python -m mymarket.mcp_server`: start the stdio MCP server.
- `npx @modelcontextprotocol/inspector uv run python -m mymarket.mcp_server`: inspect and exercise MCP tools.

## Coding Style & Naming Conventions

Use four-space indentation, `snake_case` modules and functions, `PascalCase` classes, and descriptive product keys such as `cooking_oil`. Keep products and feeds configuration-driven. No formatter or linter is configured yet. Send MCP logs to stderr and return structured JSON errors with `error` and `hint` fields.

## Testing Guidelines

Use pytest with `test_*.py` files. Cover aliases, artifact contracts, exact-date prices, provider fallback, migrations, forward scoring, and MCP responses. Routine tests must stay offline. Keep fixtures separate from real inputs; every fixture response is synthetic. No coverage percentage is specified. Real metrics come from the teammate's chronological evaluation with a 14-day purge and required baselines.

## Commit & Pull Request Guidelines

The initial commit uses a concise imperative subject. Follow that style, such as `Add RSS ingestion cache`. PRs should explain behavior, link relevant requirements or issues, and report validation results. Label fixture metrics as fake.

## Security & Data Boundaries

Keep secrets in `.env`; provide `.env.example`. Respect robots.txt, use plain Scrapling `Fetcher` without impersonation, and limit requests to one per second per host. MCP consumes processed price indexes. Load only trusted Colab joblib exports and validate hashes and package versions. Real mode must never substitute fake data.
