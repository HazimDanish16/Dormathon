"""Configuration validation and path resolution checks."""

from pathlib import Path

import pytest
from pydantic import ValidationError

from mymarket.config import Product, Settings, SourcesConfig, load_products, load_sources

ROOT = Path(__file__).resolve().parents[1]


def test_repository_configuration():
    settings = Settings(ROOT, ROOT / "config")
    products = load_products(settings).domains["staple_food"].products
    assert set(products) == {"rice", "egg", "cooking_oil", "chicken"}
    assert "ayam brand" in products["chicken"].exclude_phrases
    assert all(product.item_codes == [] for product in products.values())
    sources = load_sources(settings).sources
    assert sources["bernama"].date_from_article
    assert not sources["fmt"].enabled


@pytest.mark.parametrize("data", [
    {"aliases_en": []},
    {"aliases_en": ["chicken"], "item_codes": [-1]},
    {"aliases_en": ["chicken"], "typo": True},
])
def test_reject_invalid_product_configuration(data):
    with pytest.raises(ValidationError):
        Product.model_validate(data)


def test_reject_non_http_feed_url():
    with pytest.raises(ValidationError):
        SourcesConfig.model_validate({"sources": {"test": {"name": "Test", "url": "file:///tmp/feed"}}})


def test_settings_resolve_dotenv_paths_without_using_cwd(tmp_path, monkeypatch):
    root = tmp_path / "project"
    root.mkdir()
    (root / ".env").write_text("MYMARKET_CONFIG_DIR=custom\nMYMARKET_LOG_LEVEL=DEBUG\n", encoding="utf-8")
    monkeypatch.setenv("MYMARKET_PROJECT_ROOT", str(root))
    monkeypatch.delenv("MYMARKET_CONFIG_DIR", raising=False)
    monkeypatch.delenv("MYMARKET_LOG_LEVEL", raising=False)
    monkeypatch.chdir(tmp_path)
    settings = Settings.from_env()
    assert settings.config_dir == root / "custom"
    assert settings.log_level == "DEBUG"
    monkeypatch.setenv("MYMARKET_LOG_LEVEL", "WARNING")
    assert Settings.from_env().log_level == "WARNING"


def test_reject_invalid_log_level(monkeypatch):
    monkeypatch.setenv("MYMARKET_LOG_LEVEL", "VERBOSE")
    with pytest.raises(ValueError, match="MYMARKET_LOG_LEVEL"):
        Settings.from_env()
