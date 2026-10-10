"""Validated repository configuration, independent of the working directory."""

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated

import yaml
from dotenv import dotenv_values
from pydantic import BaseModel, ConfigDict, Field, HttpUrl


class ConfigModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Product(ConfigModel):
    aliases_en: list[str] = Field(min_length=1)
    aliases_ms: list[str] = Field(default_factory=list)
    item_codes: list[Annotated[int, Field(ge=0)]] = Field(default_factory=list)
    exclude_phrases: list[str] = Field(default_factory=list)


class Domain(ConfigModel):
    products: dict[str, Product] = Field(min_length=1)


class ProductsConfig(ConfigModel):
    domains: dict[str, Domain] = Field(min_length=1)


class Source(ConfigModel):
    name: str = Field(min_length=1)
    url: HttpUrl
    enabled: bool = True
    date_from_article: bool = False


class SourcesConfig(ConfigModel):
    sources: dict[str, Source] = Field(min_length=1)


@dataclass(frozen=True)
class Settings:
    project_root: Path
    config_dir: Path
    log_level: str = "INFO"

    @classmethod
    def from_env(cls) -> "Settings":
        root = Path(os.environ.get("MYMARKET_PROJECT_ROOT", Path(__file__).resolve().parents[2])).resolve()
        values = {**dotenv_values(root / ".env"), **os.environ}
        config_dir = Path(values.get("MYMARKET_CONFIG_DIR") or "config")
        if not config_dir.is_absolute():
            config_dir = root / config_dir
        level = (values.get("MYMARKET_LOG_LEVEL") or "INFO").upper()
        if level not in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}:
            raise ValueError("MYMARKET_LOG_LEVEL must be DEBUG, INFO, WARNING, ERROR, or CRITICAL")
        return cls(root, config_dir.resolve(), level)


def load_products(settings: Settings) -> ProductsConfig:
    with (settings.config_dir / "products.yaml").open(encoding="utf-8") as file:
        return ProductsConfig.model_validate(yaml.safe_load(file))


def load_sources(settings: Settings) -> SourcesConfig:
    with (settings.config_dir / "sources.yaml").open(encoding="utf-8") as file:
        return SourcesConfig.model_validate(yaml.safe_load(file))
