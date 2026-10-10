"""One polling pass over enabled feeds, persisting articles for MCP queries."""

import calendar
import logging
from datetime import datetime, timezone
from urllib.parse import urljoin

import feedparser
import httpx

from mymarket.config import Settings, load_sources
from mymarket.errors import AppError
from mymarket.ingest.fetch_body import fetch_body, plain_text
from mymarket.ingest.network import FetchPolicy, USER_AGENT
from mymarket.store.db import Article, ArticleStore, canonical_url

logger = logging.getLogger(__name__)


def poll_news(settings: Settings, client: httpx.Client | None = None,
              policy: FetchPolicy | None = None) -> dict:
    if settings.data_mode == "fixture":
        raise AppError("Live polling is disabled in fixture mode.", "Use real mode for live feeds; fixtures must remain synthetic.")
    sources = load_sources(settings).sources
    store = ArticleStore(settings.sqlite_path)
    owns_client = client is None
    client = client or httpx.Client(timeout=15, headers={"User-Agent": USER_AGENT})
    policy = policy or FetchPolicy(client)
    statuses = {}
    try:
        for source_id, source in sources.items():
            if not source.enabled:
                statuses[source_id] = {"status": "disabled", "items": 0, "inserted": 0}
                continue
            result = {"status": "ok", "items": 0, "inserted": 0, "duplicates": 0,
                      "skipped": 0, "newest_published_at": None}
            statuses[source_id] = result
            try:
                response = policy.get(str(source.url))
                parsed = feedparser.parse(response.content)
                if not parsed.get("version"):
                    raise ValueError("Response is not a recognized RSS or Atom feed")
                if parsed.get("bozo"):
                    logger.warning("Feed has parse warnings: %s", source_id)
                    result["status"] = "warning"
                result["items"] = len(parsed.entries)
                for entry in parsed.entries:
                    try:
                        now = datetime.now(timezone.utc)
                        title = plain_text(entry.get("title", ""))
                        link = entry.get("link")
                        if not title or not link:
                            raise ValueError("Entry needs a title and URL")
                        url = canonical_url(urljoin(str(response.url), link))
                        stamp = entry.get("published_parsed")
                        published_at = datetime.fromtimestamp(calendar.timegm(stamp), timezone.utc) if stamp else now
                        if stamp:
                            timestamp = published_at.isoformat()
                            if result["newest_published_at"] is None or timestamp > result["newest_published_at"]:
                                result["newest_published_at"] = timestamp
                        if store.is_duplicate(url, title, published_at):
                            result["duplicates"] += 1
                            continue
                        summary = plain_text(entry.get("summary", ""))
                        content = "\n".join(part.get("value", "") for part in entry.get("content", []))
                        body = fetch_body(url, summary, content, policy, need_date=not bool(stamp))
                        if not stamp and body.published_at:
                            published_at = body.published_at
                        article = Article(
                            url, title, source_id, published_at, summary, body.text,
                            entry.get("language") or parsed.feed.get("language") or "en",
                            now, date_estimated=not stamp and body.published_at is None, body_source=body.source,
                        )
                        if store.insert(article):
                            result["inserted"] += 1
                        else:
                            result["duplicates"] += 1
                        timestamp = published_at.astimezone(timezone.utc).isoformat()
                        if result["newest_published_at"] is None or timestamp > result["newest_published_at"]:
                            result["newest_published_at"] = timestamp
                    except Exception:
                        result["skipped"] += 1
                        logger.warning("Skipping malformed feed entry from %s", source_id, exc_info=True)
            except Exception as exc:
                result["status"] = "error"
                result["error"] = str(exc)
                logger.warning("Feed failed: %s", source_id, exc_info=True)
            result["newest_published_at"] = store.latest_published(source_id)
            logger.info("Feed %s: %s", source_id, result)
    finally:
        if owns_client:
            client.close()
    return {"sources": statuses, "database": str(settings.sqlite_path)}
