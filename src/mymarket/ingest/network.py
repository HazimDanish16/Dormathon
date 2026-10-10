"""Shared host throttling and conservative robots.txt enforcement."""

import time
from urllib.parse import urljoin, urlsplit
from urllib.robotparser import RobotFileParser

import httpx

from mymarket.store.db import canonical_url

USER_AGENT = "MyMarketBot/0.1"


class FetchPolicy:
    def __init__(self, client: httpx.Client, clock=time.monotonic, sleep=time.sleep):
        self.client = client
        self.clock = clock
        self.sleep = sleep
        self.last_request: dict[str, float] = {}
        self.robots: dict[str, RobotFileParser | None] = {}

    def wait(self, url: str, interval: float = 1.0):
        host = urlsplit(url).netloc.lower()
        remaining = interval - (self.clock() - self.last_request.get(host, float("-inf")))
        if remaining > 0:
            self.sleep(remaining)
        self.last_request[host] = self.clock()

    def check(self, url: str):
        url = canonical_url(url)
        parts = urlsplit(url)
        origin = f"{parts.scheme}://{parts.netloc}"
        if origin not in self.robots:
            robots_url = origin + "/robots.txt"
            self.wait(robots_url)
            parser = RobotFileParser(robots_url)
            try:
                response = self.client.get(robots_url, follow_redirects=False)
                if response.status_code in {404, 410}:
                    parser.parse([])
                elif response.status_code == 200:
                    parser.parse(response.text.splitlines())
                else:
                    raise PermissionError("robots.txt unavailable")
                self.robots[origin] = parser
            except (httpx.HTTPError, PermissionError):
                self.robots[origin] = None
        parser = self.robots[origin]
        if parser is None or not parser.can_fetch(USER_AGENT, url):
            raise PermissionError("robots.txt blocks this request or could not be read")
        interval = max(1.0, float(parser.crawl_delay(USER_AGENT) or 0))
        request_rate = parser.request_rate(USER_AGENT)
        if request_rate and request_rate.requests:
            interval = max(interval, request_rate.seconds / request_rate.requests)
        self.wait(url, interval)

    def get(self, url: str, article: bool = False):
        for _ in range(6):
            self.check(url)
            if article:
                from scrapling.fetchers import Fetcher

                response = Fetcher.get(
                    url, headers={"User-Agent": USER_AGENT}, timeout=15, retries=0,
                    follow_redirects=False, impersonate=None, stealthy_headers=False,
                )
                status = response.status
            else:
                response = self.client.get(url, follow_redirects=False)
                status = response.status_code
            if status in {301, 302, 303, 307, 308}:
                location = response.headers.get("location") or response.headers.get("Location")
                if not location:
                    raise ValueError("Redirect has no location")
                url = canonical_url(urljoin(url, location))
                continue
            if status >= 400:
                raise ValueError(f"HTTP {status}")
            return response
        raise ValueError("Too many redirects")
