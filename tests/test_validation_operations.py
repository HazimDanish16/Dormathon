"""Migration preservation, outcome maturity, and maintenance failure reporting."""

import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

from mymarket.config import Settings
from mymarket.fixtures import generate
from mymarket.maintenance import daily_refresh, validate_handoff
from mymarket.model.predict import Predictor
from mymarket.store.db import Article, ArticleStore
from mymarket.store.validation import PredictionLedger

ROOT = Path(__file__).resolve().parents[1]


def settings_for(tmp_path):
    generate(tmp_path)
    return Settings(ROOT, ROOT / "config", data_mode="fixture", data_dir=tmp_path, database_path=tmp_path / "FAKE.sqlite3")


def test_migrations_preserve_legacy_news(tmp_path):
    path = tmp_path / "legacy.sqlite3"
    db = sqlite3.connect(path)
    db.executescript("""CREATE TABLE articles (id INTEGER PRIMARY KEY, url TEXT UNIQUE, title TEXT, source TEXT,
        published_at TEXT, summary TEXT, body TEXT, lang TEXT, fetched_at TEXT);
        INSERT INTO articles VALUES (1, 'https://example.com/', 'Original', 'test', '2025-01-01T00:00:00+00:00', '', '', 'en', '2025-01-01T00:00:00+00:00');""")
    db.close()
    store = ArticleStore(path)
    ArticleStore(path)
    with store.connection() as db:
        assert db.execute("PRAGMA user_version").fetchone()[0] == 2
        assert db.execute("SELECT title FROM articles").fetchone()[0] == "Original"
        assert "target_date" in {row["name"] for row in db.execute("PRAGMA table_info(predictions)")}


def test_maturity_estimates_and_idempotence(tmp_path):
    settings = settings_for(tmp_path)
    store = ArticleStore(settings.sqlite_path)
    now = datetime(2025, 7, 1, tzinfo=timezone.utc)
    ledger = PredictionLedger(settings)
    prediction = Predictor(settings).predict("Chicken shortage", [("chicken", "staple_food")])[0]
    for i, estimated in enumerate([False, True]):
        store.insert(Article(f"https://example.com/{i}", f"Article {i} unique {'chicken' if i == 0 else 'egg'}", "FAKE", now, "", "", "en", now, estimated))
    rows = store.recent(now=now)
    for article in rows:
        first = ledger.log(article, prediction, now=now)
        assert ledger.log(article, prediction, now=now) == first
    assert ledger.score(now=now + timedelta(days=13))["scored"] == 0
    assert ledger.score(now=now + timedelta(days=15))["scored"] == 1
    assert ledger.score(now=now + timedelta(days=16))["scored"] == 0
    report = ledger.report()
    assert report["logged"] == 2
    assert report["scored"] == 1
    assert report["excluded"] == 1
    assert report["accuracy"] in [0., 1.]


def test_missing_prices_stay_pending(tmp_path):
    settings = settings_for(tmp_path)
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    store = ArticleStore(settings.sqlite_path)
    store.insert(Article("https://example.com/article", "Egg supply story", "FAKE", now, "", "", "en", now))
    ledger = PredictionLedger(settings)
    ledger.log(store.recent(now=now)[0], Predictor(settings).predict("Egg", [("egg", "staple_food")])[0], now=now)
    assert ledger.score(now=now + timedelta(days=15))["missing_price_windows"] == 1
    assert ledger.report()["pending"] == 1


def test_abstentions_retrospective_and_text_predictions_are_excluded(tmp_path):
    settings = settings_for(tmp_path)
    now = datetime(2025, 7, 1, tzinfo=timezone.utc)
    store = ArticleStore(settings.sqlite_path)
    store.insert(Article("https://example.com/excluded", "Chicken shortage", "FAKE", now, "", "", "en", now))
    article = store.recent(now=now)[0]
    prediction = Predictor(settings).predict("Chicken", [("chicken", "staple_food")])[0]
    ledger = PredictionLedger(settings)
    ledger.log(article, {**prediction, "abstained": True}, now=now)
    ledger.log(article, {**prediction, "model_version": "FAKE-retrospective"}, now=now + timedelta(days=20))
    text_article = store.record_text("Egg supply")
    ledger.log(text_article, prediction)
    assert len(store.recent(now=now)) == 1
    assert ledger.score(now=now + timedelta(days=30))["scored"] == 0
    assert ledger.report()["excluded"] == 3


def test_handoff_coverage_and_incomplete_daily_refresh(tmp_path):
    settings = settings_for(tmp_path)
    assert validate_handoff(settings)["ready"] is True
    settings.data_file("price_index.parquet").unlink()
    report = daily_refresh(settings)
    assert report["status"] == "incomplete"
    assert report["errors"]
