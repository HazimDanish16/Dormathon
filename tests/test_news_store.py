"""Cache persistence, deduplication, and time-window checks."""

from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest

from mymarket.store.db import Article, ArticleStore, canonical_url

NOW = datetime(2026, 10, 10, 4, tzinfo=timezone.utc)


def article(**changes):
    return replace(Article("https://example.com/story", "Chicken feed costs rise",
                           "malay_mail", NOW, "Summary", "Body", "en", NOW), **changes)


def test_url_and_near_title_deduplication_persist(tmp_path):
    path = tmp_path / "news.sqlite3"
    store = ArticleStore(path)
    assert store.insert(article(url="https://example.com/story?utm_source=rss#top"))
    assert not ArticleStore(path).insert(article(title="Updated headline"))
    assert not store.insert(article(url="https://other.example/story", title="Chicken feed costs rise!"))
    assert store.insert(article(url="https://example.com/later", published_at=NOW + timedelta(days=4)))


def test_recent_filters_time_sources_and_limit(tmp_path):
    store = ArticleStore(tmp_path / "news.sqlite3")
    assert store.insert(article())
    assert store.insert(article(url="https://example.com/eggs", title="Egg supply improves", source="bernama",
                                published_at=NOW - timedelta(hours=2), date_estimated=True))
    assert store.insert(article(url="https://example.com/old", title="Rice export restrictions",
                                published_at=NOW - timedelta(days=5)))
    assert len(store.recent(now=NOW)) == 2
    assert len(store.recent(now=NOW, limit=1)) == 1
    rows = store.recent(now=NOW, sources=["bernama"])
    assert rows[0]["date_estimated"] is True
    assert rows[0]["published_at"].endswith("+08:00")
    assert "body" not in rows[0]
    assert store.recent(now=NOW, sources=[]) == []
    assert store.recent(now=NOW, sources=["' OR 1=1 --"]) == []
    with pytest.raises(ValueError):
        store.recent(hours=0)


def test_future_articles_are_not_returned(tmp_path):
    store = ArticleStore(tmp_path / "news.sqlite3")
    assert store.insert(article(published_at=NOW + timedelta(hours=1)))
    assert store.recent(now=NOW) == []


@pytest.mark.parametrize("url", ["file:///tmp/data", "javascript:alert(1)", "https://user:pass@example.com/"])
def test_reject_invalid_article_urls(url):
    with pytest.raises(ValueError):
        canonical_url(url)
