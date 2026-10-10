"""Contract checks and bilingual relevance behavior with a named test double."""

from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pytest

from mymarket.config import Settings, load_products
from mymarket.contracts import SCHEMAS, read_data, validate_frame
from mymarket.errors import AppError
from mymarket.filter.aliases import match_aliases
from mymarket.filter.embed_filter import filter_threshold
from mymarket.service import MarketService
from mymarket.store.db import Article, ArticleStore
from mymarket.fixtures import generate

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def fixture_settings(tmp_path):
    generate(tmp_path)
    return Settings(ROOT, ROOT / "config", database_path=tmp_path / "FAKE.sqlite3", data_mode="fixture", data_dir=tmp_path)


def test_fixture_schemas_and_real_isolation(fixture_settings):
    for name in SCHEMAS:
        frame = read_data(fixture_settings, name)
        assert len(frame) > 0
        with pytest.raises(AppError, match="Synthetic"):
            validate_frame(frame, name, replace(fixture_settings, data_mode="real"))
    assert len(read_data(fixture_settings, "examples.parquet")) == 500
    assert len(read_data(fixture_settings, "news_clean.parquet")) == 200
    frame = read_data(fixture_settings, "price_index.parquet")
    frame.loc[0, "index"] = 0
    with pytest.raises(ValueError):
        validate_frame(frame, "price_index.parquet", fixture_settings)


@pytest.mark.parametrize("text, products", [
    ("Harga ayam meningkat", {"chicken"}), ("Eggplant exports increase", set()),
    ("Ayam Brand sardines", set()), ("Chicken rice shop opens", set()),
    ("Nasi goreng is popular", set()), ("Harga beras dan minyak masak naik", {"rice", "cooking_oil"}),
])
def test_alias_boundaries_and_exclusions(text, products):
    config = load_products(Settings(ROOT, ROOT / "config"))
    assert {match["product"] for match in match_aliases(text, config)} == products


def test_relevance_threshold_persistence_and_errors(fixture_settings):
    store = ArticleStore(fixture_settings.sqlite_path)
    now = datetime.now(timezone.utc)
    store.insert(Article("https://example.com/FAKE", "Chicken shortage", "FAKE", now, "", "", "en", now))
    service = MarketService(fixture_settings)
    assert service.filter_relevant()["count"] == 1
    with store.connection() as db:
        assert db.execute("SELECT COUNT(*) FROM article_products").fetchone()[0] == 1
    service.embedder.encode = lambda texts: np.array([[1., 0.], [0., 1.]])
    assert service.filter_relevant()["count"] == 0
    with store.connection() as db:
        assert db.execute("SELECT COUNT(*) FROM article_products").fetchone()[0] == 0
    with pytest.raises(AppError):
        service.filter_relevant(domain="unknown")
    assert filter_threshold(fixture_settings) == (.8, False)


def test_changed_aliases_remove_stale_matches(fixture_settings):
    store = ArticleStore(fixture_settings.sqlite_path)
    now = datetime.now(timezone.utc)
    store.insert(Article("https://example.com/FAKE-changed", "Chicken shortage", "FAKE", now, "", "", "en", now))
    service = MarketService(fixture_settings)
    assert service.filter_relevant()["count"] == 1
    chicken = next(domain.products["chicken"] for domain in service.config.domains.values() if "chicken" in domain.products)
    chicken.exclude_phrases.append("chicken shortage")
    assert service.filter_relevant()["count"] == 0
    with store.connection() as db:
        assert db.execute("SELECT COUNT(*) FROM article_products").fetchone()[0] == 0
