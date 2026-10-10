"""Deterministic network-policy, body fallback, and RSS pipeline checks."""

from types import SimpleNamespace

import httpx
import pytest

from mymarket.config import Settings
from mymarket.ingest.fetch_body import fetch_body
from mymarket.ingest.network import FetchPolicy
from mymarket.ingest.rss import poll_news
from mymarket.store.db import ArticleStore


def policy_for(handler):
    ticks = [0.0]
    client = httpx.Client(transport=httpx.MockTransport(handler))
    policy = FetchPolicy(client, clock=lambda: ticks[0], sleep=lambda delay: ticks.__setitem__(0, ticks[0] + delay))
    return client, policy, ticks


def test_robots_throttle_and_redirect_checks():
    visited = []
    def handler(request):
        visited.append(str(request.url))
        if request.url.path == "/robots.txt":
            return httpx.Response(200, text="User-agent: *\nDisallow: /blocked\nCrawl-delay: 2\n")
        if request.url.path == "/redirect":
            return httpx.Response(302, headers={"Location": "/blocked"})
        return httpx.Response(200, text="content")
    client, policy, ticks = policy_for(handler)
    with client:
        policy.get("https://example.com/open")
        policy.get("https://example.com/another")
        assert ticks[0] == 4
        assert visited.count("https://example.com/robots.txt") == 1
        with pytest.raises(PermissionError):
            policy.get("https://example.com/redirect")
        assert "https://example.com/blocked" not in visited


@pytest.mark.parametrize("status", [403, 500, 302])
def test_unavailable_robots_prevents_fetch(status):
    visited = []
    def handler(request):
        visited.append(request.url.path)
        return httpx.Response(status)
    client, policy, _ = policy_for(handler)
    with client, pytest.raises(PermissionError):
        policy.get("https://example.com/article")
    assert visited == ["/robots.txt"]


def test_plain_fetcher_options_disable_browser_impersonation(monkeypatch):
    from scrapling.fetchers import Fetcher
    calls = []
    def fake_get(url, **kwargs):
        calls.append(kwargs)
        return SimpleNamespace(status=200)
    monkeypatch.setattr(Fetcher, "get", fake_get)
    client, policy, _ = policy_for(lambda request: httpx.Response(404))
    with client:
        policy.get("https://example.com/article", article=True)
    assert calls[0]["impersonate"] is None
    assert calls[0]["stealthy_headers"] is False
    assert calls[0]["follow_redirects"] is False
    assert calls[0]["retries"] == 0


def test_full_rss_content_skips_article_fetch():
    def fail(*args, **kwargs):
        raise AssertionError("Should not fetch full RSS content")
    result = fetch_body("https://example.com/article", "Summary", "<p>" + "Full story. " * 40 + "</p>",
                        SimpleNamespace(get=fail))
    assert result.source == "rss_content"
    assert "<p>" not in result.text


def test_body_failure_falls_back_to_summary():
    def fail(*args, **kwargs):
        raise PermissionError("Blocked")
    result = fetch_body("https://example.com/article", "RSS summary", "", SimpleNamespace(get=fail))
    assert result.text == "RSS summary"
    assert result.source == "rss_summary"


def test_short_or_paywalled_body_falls_back_to_summary():
    class Page:
        def css(self, selector):
            return SimpleNamespace(getall=lambda: ["false"] if "isAccessibleForFree" in selector else [])
        def markdown(self, **kwargs):
            raise AssertionError("Paywalled text must not be used")
    result = fetch_body("https://example.com/article", "RSS summary", "",
                        SimpleNamespace(get=lambda *args, **kwargs: Page()))
    assert result.source == "rss_summary"


def test_article_date_and_short_body_fallback():
    class Page:
        def css(self, selector):
            values = ['{"datePublished": "2026-10-10T12:00:00+08:00"}'] if "ld+json" in selector else []
            return SimpleNamespace(getall=lambda: values)
        def markdown(self, **kwargs):
            return "Too short"
    result = fetch_body("https://example.com/article", "Summary", "",
                        SimpleNamespace(get=lambda *args, **kwargs: Page()), need_date=True)
    assert result.source == "rss_summary"
    assert result.published_at.isoformat() == "2026-10-10T12:00:00+08:00"


def test_jsonld_paywall_is_not_used():
    class Page:
        def css(self, selector):
            values = ['{"@graph": [{"isAccessibleForFree": false}]}'] if "ld+json" in selector else []
            return SimpleNamespace(getall=lambda: values)
        def markdown(self, **kwargs):
            raise AssertionError("Paywall detected")
    result = fetch_body("https://example.com/article", "Summary", "",
                        SimpleNamespace(get=lambda *args, **kwargs: Page()))
    assert result.source == "rss_summary"


def test_poll_continues_after_source_failure_and_caches_articles(tmp_path):
    config = tmp_path / "config"
    config.mkdir()
    (config / "sources.yaml").write_text("""sources:
  broken:
    name: Broken
    url: https://example.com/broken
  working:
    name: Working
    url: https://example.com/feed
  disabled:
    name: Disabled
    url: https://example.com/disabled
    enabled: false
""", encoding="utf-8")
    content = "Full RSS story about chicken feed prices. " * 15
    rss = f"""<rss version="2.0" xmlns:content="http://purl.org/rss/1.0/modules/content/">
      <channel><title>News</title><item><title>Chicken feed costs rise</title>
      <link>https://example.com/article</link><pubDate>Sat, 10 Oct 2026 04:00:00 GMT</pubDate>
      <description>Summary</description><content:encoded><![CDATA[{content}]]></content:encoded>
      </item><item><title>No date</title><link>https://example.com/no-date</link>
      <description>Fallback summary</description></item><item><title>Missing link</title></item></channel></rss>"""
    visited = []
    def handler(request):
        visited.append(request.url.path)
        if request.url.path == "/robots.txt":
            return httpx.Response(200, text="User-agent: *\nDisallow: /no-date\n")
        if request.url.path == "/feed":
            return httpx.Response(200, text=rss)
        return httpx.Response(500)
    client, policy, _ = policy_for(handler)
    settings = Settings(tmp_path, config)
    with client:
        report = poll_news(settings, client, policy)
        assert report["sources"]["broken"]["status"] == "error"
        assert report["sources"]["working"]["inserted"] == 2
        assert report["sources"]["working"]["skipped"] == 1
        repeat = poll_news(settings, client, policy)
        assert repeat["sources"]["working"]["duplicates"] == 2
        assert repeat["sources"]["working"]["newest_published_at"] is not None
        assert repeat["sources"]["working"]["newest_published_at"] == report["sources"]["working"]["newest_published_at"]
    assert "/article" not in visited
    assert "/no-date" not in visited
    assert "/disabled" not in visited
    with ArticleStore(settings.sqlite_path).connection() as db:
        rows = db.execute("SELECT * FROM articles ORDER BY id").fetchall()
        assert rows[0]["body_source"] == "rss_content"
        assert rows[1]["date_estimated"] == 1
