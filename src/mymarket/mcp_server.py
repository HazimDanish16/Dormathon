"""Stdio tools for configuration and cached news, with placeholders for ML."""

import logging
import sys
from typing import Any

from mcp.server.fastmcp import FastMCP

from mymarket.config import Settings, load_products, load_sources
from mymarket.store.db import ArticleStore
from mymarket.errors import AppError
from mymarket.service import MarketService

logger = logging.getLogger(__name__)


def create_server(settings: Settings | None = None) -> FastMCP:
    settings = settings or Settings.from_env()
    service = None
    def app():
        nonlocal service
        if service is None:
            service = MarketService(settings)
        return service

    def invoke(method, **kwargs):
        try:
            return getattr(app(), method)(**kwargs)
        except AppError as exc:
            return exc.payload()
        except Exception:
            logger.exception("Tool failed: %s", method)
            return {"error": "Unable to complete request.", "hint": "Check server logs, configuration, and handoff inputs."}
    server = FastMCP(
        "mymarket",
        instructions=(
            "Malaysian news and product-price awareness. Predictions require compatible teammate Colab exports. "
            "Fixture outputs are explicitly synthetic. Awareness only, not financial advice."
        ),
        log_level=settings.log_level,
    )

    @server.tool()
    def list_domains() -> dict[str, Any]:
        """List configured domains, products, English/Malay aliases, and item mappings."""
        try:
            return {**load_products(settings).model_dump(mode="json"), "synthetic": settings.data_mode == "fixture"}
        except Exception:
            logger.exception("Unable to load product configuration")
            return {
                "error": "Unable to load product configuration.",
                "hint": "Check config/products.yaml and MYMARKET_CONFIG_DIR against the documented schema.",
            }

    @server.tool()
    def fetch_news(hours: int = 48, sources: list[str] | None = None, limit: int = 100) -> dict[str, Any]:
        """Read cached news, filtered by source IDs. Poll feeds separately to refresh the cache."""
        try:
            if not 1 <= hours <= 8760 or not 1 <= limit <= 1000:
                return {"error": "Invalid news query.", "hint": "Use hours=1..8760 and limit=1..1000."}
            if sources is not None:
                known_sources = load_sources(settings).sources
                if any(source not in known_sources for source in sources):
                    return {"error": "Unknown news source.", "hint": "Use source IDs from config/sources.yaml."}
            articles = ArticleStore(settings.sqlite_path).recent(hours, sources, limit)
            return {"articles": articles, "count": len(articles), "synthetic": settings.data_mode == "fixture"}
        except Exception:
            logger.exception("Unable to read cached news")
            return {"error": "Unable to read cached news.",
                    "hint": "Check MYMARKET_DATABASE_PATH and run scripts/poll_news.py to populate the cache."}

    @server.tool()
    def filter_relevant(domain: str | None = None, hours: int = 48) -> dict[str, Any]:
        """Match cached articles to products using bilingual aliases and CPU embeddings."""
        return invoke("filter_relevant", domain=domain, hours=hours)

    @server.tool()
    def predict_impact(
        url: str | None = None, text: str | None = None, products: list[str] | None = None,
    ) -> dict[str, Any]:
        """Predict price direction using a trusted Colab export; accepts text or a cached URL."""
        return invoke("predict_impact", url=url, text=text, products=products)

    @server.tool()
    def price_context(product: str, days: int = 90) -> dict[str, Any]:
        """Return exact-date price changes, series, and data freshness from processed indexes."""
        return invoke("price_context", product=product, days=days)

    @server.tool()
    def scan_alerts(
        domain: str | None = None, hours: int = 48, min_confidence: float = 0.55, lang: str = "en",
    ) -> dict[str, Any]:
        """Combine cached relevant news, price predictions, context, and grounded explanations."""
        return invoke("scan_alerts", domain=domain, hours=hours, min_confidence=min_confidence, lang=lang)

    @server.tool()
    def backtest_report(product: str | None = None) -> dict[str, Any]:
        """Read validated Colab evaluation results; never invent accuracy or baselines."""
        return invoke("backtest_report", product=product)

    @server.tool()
    def forward_validation(product: str | None = None) -> dict[str, Any]:
        """Report matured scored predictions, pending outcomes, exclusions, and per-model accuracy."""
        return invoke("forward_validation", product=product)

    return server


def main() -> None:
    logging.basicConfig(level=logging.INFO, stream=sys.stderr)
    try:
        settings = Settings.from_env()
        logging.getLogger().setLevel(settings.log_level)
        load_products(settings)
        load_sources(settings)
    except Exception:
        logger.exception("Invalid configuration; check .env and config/*.yaml")
        raise SystemExit(2)
    create_server(settings).run(transport="stdio")


if __name__ == "__main__":
    main()
