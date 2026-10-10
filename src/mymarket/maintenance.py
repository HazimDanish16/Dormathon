"""Handoff readiness checks and daily orchestration without owning data training."""

import json
import subprocess
from datetime import timedelta
import math

from mymarket.config import Settings, load_products
from mymarket.contracts import SCHEMAS, read_data
from mymarket.errors import AppError
from mymarket.ingest.rss import poll_news
from mymarket.service import MarketService


def validate_handoff(settings: Settings):
    frames = {name: read_data(settings, name) for name in SCHEMAS}
    config = load_products(settings)
    products = {product for domain in config.domains.values() for product in domain.products}
    mapping = frames["item_mapping.csv"]
    if set(mapping["product"]) != products:
        raise AppError("Item mapping does not cover all configured products.", "Obtain reviewed mappings for each tracked product.")
    prices = frames["price_index.parquet"]
    available = set(zip(prices["product"], prices["date"]))
    values = prices.set_index(["product", "date"])["index"].to_dict()
    news = frames["news_clean.parquet"].set_index("article_id")["published_at"].to_dict()
    for row in frames["examples.parquet"].itertuples():
        day = row.published_at.tz_convert("Asia/Kuala_Lumpur").date()
        if news.get(row.article_id) != row.published_at or any((row.product, day + timedelta(days=offset)) not in available for offset in [-15, -1, 14]):
            raise AppError("Example IDs or price windows do not match the handoff.", "Align cleaned news, examples, and exact base/momentum/target dates.")
        if settings.data_mode == "real":
            expected = values[(row.product, day + timedelta(days=14))] / values[(row.product, day - timedelta(days=1))] - 1
            momentum = values[(row.product, day - timedelta(days=1))] / values[(row.product, day - timedelta(days=15))] - 1
            if not math.isclose(expected, row.realized_return, abs_tol=1e-6) or not math.isclose(momentum, row.momentum_return, abs_tol=1e-6):
                raise AppError("Example returns disagree with processed prices.", "Use fractional returns and the exact horizon/base/momentum dates in the handoff contract.")
    service = MarketService(settings)
    sample = frames["examples.parquet"].iloc[0]
    service.predictor.predict(sample["text"], [(sample["product"], sample["domain"])])
    return {"ready": True, "synthetic": service.synthetic, "rows": {name: len(frame) for name, frame in frames.items()},
            "model_version": service.predictor.metadata()["model_version"]}


def daily_refresh(settings: Settings, poll=poll_news, runner=subprocess.run):
    report = {"status": "ok", "synthetic": settings.data_mode == "fixture", "errors": []}
    if settings.data_mode == "fixture":
        report["news"] = {"status": "fixture", "message": "Live polling skipped."}
    else:
        try:
            report["news"] = poll(settings)
            enabled = [source for source in report["news"]["sources"].values() if source["status"] != "disabled"]
            if not enabled or any(source["status"] == "error" for source in enabled):
                report["errors"].append("One or more news sources failed or none were enabled.")
        except Exception:
            report["errors"].append("News refresh failed; check configuration and feed logs.")
    command = settings.environment().get("MYMARKET_PRICE_REFRESH_COMMAND")
    if command and settings.data_mode == "real":
        try:
            args = json.loads(command)
            if not isinstance(args, list) or not args or not all(isinstance(arg, str) for arg in args):
                raise ValueError("Expected a nonempty JSON argument list")
            result = runner(args, cwd=settings.project_root, timeout=600, capture_output=True, text=True, check=False)
            if result.returncode:
                raise ValueError("Price-refresh command failed")
            report["price_refresh"] = "completed"
        except Exception:
            report["errors"].append("Price refresh failed; check the data-team command and run it directly for details.")
    else:
        report["price_refresh"] = "not configured" if settings.data_mode == "real" else "fixture"
        if settings.data_mode == "real":
            report["errors"].append("No price-refresh command configured; using existing processed data only.")
    service = MarketService(settings)
    try:
        report["handoff"] = validate_handoff(settings)
    except AppError as exc:
        report["handoff"] = exc.payload()
        report["errors"].append(exc.error)
    for name, operation in [("alerts", service.scan_alerts), ("outcomes", service.ledger.score)]:
        try:
            report[name] = operation()
        except AppError as exc:
            report[name] = exc.payload()
            report["errors"].append(exc.error)
        except Exception:
            report[name] = {"error": "Operation failed.", "hint": "Check data inputs and server logs."}
            report["errors"].append(f"{name} failed")
    if report["errors"]:
        report["status"] = "incomplete"
    return report
