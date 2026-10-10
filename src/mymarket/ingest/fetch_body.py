"""Article text extraction with RSS-first and summary fallback behavior."""

import logging
import json
from dataclasses import dataclass
from datetime import datetime

from lxml import html

from mymarket.ingest.network import FetchPolicy

logger = logging.getLogger(__name__)


def plain_text(value: str) -> str:
    if not value.strip():
        return ""
    try:
        root = html.fragment_fromstring(value, create_parent="div")
        for node in root.xpath(".//script | .//style"):
            node.drop_tree()
        return " ".join(root.text_content().split())
    except (ValueError, html.etree.ParserError):
        return " ".join(value.split())


def parse_article_date(value: str | None) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return result if result.tzinfo else None
    except ValueError:
        return None


@dataclass(frozen=True)
class BodyResult:
    text: str
    source: str
    published_at: datetime | None = None


def fetch_body(url: str, summary: str, content: str, policy: FetchPolicy,
               need_date: bool = False) -> BodyResult:
    full_text = plain_text(content)
    if len(full_text) >= 300 and not need_date:
        return BodyResult(full_text, "rss_content")
    try:
        page = policy.get(url, article=True)
        dates = page.css('meta[property="article:published_time"]::attr(content)').getall()
        dates += page.css('meta[name="datePublished"]::attr(content)').getall()
        dates += page.css("time::attr(datetime)").getall()
        published_at = next((date for value in dates if (date := parse_article_date(value))), None)
        # Explicit paywall metadata means the page body must not be used.
        paywall = page.css('meta[name="isAccessibleForFree"]::attr(content)').getall()
        for block in page.css('script[type="application/ld+json"]::text').getall():
            try:
                data = json.loads(block)
                nodes = data if isinstance(data, list) else [data]
                for node in nodes:
                    if isinstance(node, dict):
                        nodes.extend(node.get("@graph", []))
                        published_at = published_at or parse_article_date(node.get("datePublished"))
                        if node.get("isAccessibleForFree") is False:
                            paywall.append("false")
            except (ValueError, TypeError):
                continue
        if any(value.lower() == "false" for value in paywall):
            return BodyResult(summary, "rss_summary", published_at)
        text = page.markdown(main_content_only=True).strip()
        if len(full_text) >= 300:
            return BodyResult(full_text, "rss_content", published_at)
        if len(text) >= 300:
            return BodyResult(text, "article", published_at)
        return BodyResult(summary, "rss_summary", published_at)
    except Exception:
        logger.warning("Article body unavailable; using RSS text: %s", url, exc_info=True)
        return BodyResult(full_text if len(full_text) >= 300 else summary,
                          "rss_content" if len(full_text) >= 300 else "rss_summary")
