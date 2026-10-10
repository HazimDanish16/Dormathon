"""SQLite article cache and tables reserved for predictions and outcomes."""

import math
import re
import sqlite3
from collections import Counter
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from zoneinfo import ZoneInfo
from mymarket.errors import AppError

KL = ZoneInfo("Asia/Kuala_Lumpur")


def canonical_url(url: str) -> str:
    parts = urlsplit(url)
    if parts.scheme not in {"http", "https"} or not parts.hostname or parts.username or parts.password:
        raise ValueError("Article URLs must use HTTP or HTTPS without credentials")
    query = [(key, value) for key, value in parse_qsl(parts.query, keep_blank_values=True)
             if not key.lower().startswith("utm_") and key.lower() not in {"fbclid", "gclid"}]
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), parts.path or "/", urlencode(query), ""))


def utc_stamp(value: datetime) -> str:
    if value.tzinfo is None:
        raise ValueError("Timestamps must include a timezone")
    return value.astimezone(timezone.utc).isoformat()


def title_similarity(left: str, right: str) -> float:
    a = Counter(re.findall(r"\w+", left.casefold()))
    b = Counter(re.findall(r"\w+", right.casefold()))
    norm = math.sqrt(sum(n * n for n in a.values()) * sum(n * n for n in b.values()))
    return sum(n * b[word] for word, n in a.items()) / norm if norm else 0.0


@dataclass(frozen=True)
class Article:
    url: str
    title: str
    source: str
    published_at: datetime
    summary: str
    body: str
    lang: str
    fetched_at: datetime
    date_estimated: bool = False
    body_source: str = "rss_summary"


class ArticleStore:
    def __init__(self, path: Path):
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        with self.connection() as db:
            if db.execute("PRAGMA user_version").fetchone()[0] > 2:
                raise AppError("Database schema is newer than this app.", "Upgrade MyMarket; do not downgrade an existing database.")
            db.executescript("""
                CREATE TABLE IF NOT EXISTS articles (
                    id INTEGER PRIMARY KEY, url TEXT NOT NULL UNIQUE, title TEXT NOT NULL,
                    source TEXT NOT NULL, published_at TEXT NOT NULL, summary TEXT NOT NULL,
                    body TEXT NOT NULL, lang TEXT NOT NULL, fetched_at TEXT NOT NULL,
                    date_estimated INTEGER NOT NULL DEFAULT 0,
                    body_source TEXT NOT NULL DEFAULT 'rss_summary'
                );
                CREATE INDEX IF NOT EXISTS articles_published ON articles(published_at);
                CREATE TABLE IF NOT EXISTS article_products (
                    article_id INTEGER NOT NULL REFERENCES articles(id), product TEXT NOT NULL,
                    match_score REAL NOT NULL, matched_terms TEXT NOT NULL,
                    PRIMARY KEY(article_id, product)
                );
                CREATE TABLE IF NOT EXISTS predictions (
                    id INTEGER PRIMARY KEY, article_id INTEGER NOT NULL REFERENCES articles(id),
                    product TEXT NOT NULL, direction TEXT NOT NULL, p_up REAL NOT NULL,
                    p_down REAL NOT NULL, p_stable REAL NOT NULL, model_version TEXT NOT NULL,
                    created_at TEXT NOT NULL, horizon_days INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS outcomes (
                    prediction_id INTEGER PRIMARY KEY REFERENCES predictions(id),
                    realized_ret REAL NOT NULL, realized_label TEXT NOT NULL, scored_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS embeddings (
                    model_key TEXT NOT NULL, text_hash TEXT NOT NULL, vector TEXT NOT NULL,
                    PRIMARY KEY(model_key, text_hash)
                );
            """)
            db.execute("BEGIN IMMEDIATE")
            columns = {row["name"] for row in db.execute("PRAGMA table_info(articles)")}
            for column, definition in [("date_estimated", "INTEGER NOT NULL DEFAULT 0"), ("body_source", "TEXT NOT NULL DEFAULT 'rss_summary'")]:
                if column not in columns:
                    db.execute(f"ALTER TABLE articles ADD COLUMN {column} {definition}")
            columns = {row["name"] for row in db.execute("PRAGMA table_info(predictions)")}
            additions = {"threshold": "REAL", "base_date": "TEXT", "target_date": "TEXT",
                         "abstained": "INTEGER NOT NULL DEFAULT 0", "synthetic": "INTEGER NOT NULL DEFAULT 0",
                         "eligible": "INTEGER NOT NULL DEFAULT 0"}
            for column, definition in additions.items():
                if column not in columns:
                    db.execute(f"ALTER TABLE predictions ADD COLUMN {column} {definition}")
            db.execute("CREATE INDEX IF NOT EXISTS predictions_target ON predictions(target_date)")
            db.execute("PRAGMA user_version = 2")

    @contextmanager
    def connection(self):
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys = ON")
        try:
            with db:
                yield db
        finally:
            db.close()

    @staticmethod
    def _duplicate(db, url: str, title: str, published_at: datetime) -> bool:
        if db.execute("SELECT 1 FROM articles WHERE url = ?", (canonical_url(url),)).fetchone():
            return True
        rows = db.execute(
            "SELECT title FROM articles WHERE published_at BETWEEN ? AND ?",
            (utc_stamp(published_at - timedelta(days=3)), utc_stamp(published_at + timedelta(days=3))),
        )
        return any(title_similarity(title, row["title"]) > 0.9 for row in rows)

    def is_duplicate(self, url: str, title: str, published_at: datetime) -> bool:
        with self.connection() as db:
            return self._duplicate(db, url, title, published_at)

    def latest_published(self, source: str) -> str | None:
        with self.connection() as db:
            return db.execute("SELECT MAX(published_at) FROM articles WHERE source = ?", (source,)).fetchone()[0]

    def insert(self, article: Article) -> bool:
        with self.connection() as db:
            # Serialize the duplicate check and insert across polling processes.
            db.execute("BEGIN IMMEDIATE")
            if self._duplicate(db, article.url, article.title, article.published_at):
                return False
            db.execute("""
                INSERT INTO articles
                (url, title, source, published_at, summary, body, lang, fetched_at, date_estimated, body_source)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (canonical_url(article.url), article.title, article.source, utc_stamp(article.published_at),
                  article.summary, article.body, article.lang, utc_stamp(article.fetched_at),
                  article.date_estimated, article.body_source))
            return True

    def recent(self, hours: int = 48, sources: list[str] | None = None, limit: int = 100,
               now: datetime | None = None, include_body: bool = False) -> list[dict]:
        if not 1 <= hours <= 8760 or not 1 <= limit <= 1000:
            raise ValueError("hours must be 1..8760 and limit must be 1..1000")
        now = now or datetime.now(timezone.utc)
        query = """SELECT id, title, source, published_at, url, summary, date_estimated
                   FROM articles WHERE published_at BETWEEN ? AND ?"""
        if include_body:
            query = query.replace("summary, date_estimated", "summary, body, lang, date_estimated")
        params = [utc_stamp(now - timedelta(hours=hours)), utc_stamp(now)]
        if sources is not None:
            if not sources:
                return []
            query += " AND source IN (" + ",".join("?" for _ in sources) + ")"
            params.extend(sources)
        query += " ORDER BY published_at DESC, id DESC LIMIT ?"
        params.append(limit)
        with self.connection() as db:
            results = [dict(row) for row in db.execute(query, params)]
        for row in results:
            row["published_at"] = datetime.fromisoformat(row["published_at"]).astimezone(KL).isoformat()
            row["date_estimated"] = bool(row["date_estimated"])
        return results
