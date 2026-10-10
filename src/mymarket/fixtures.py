"""Synthetic fixture utilities. These never train a model."""

from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from mymarket.contracts import read_data
from mymarket.filter.aliases import article_text
from mymarket.errors import AppError
from mymarket.store.db import Article, ArticleStore


def generate(destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    products = ["rice", "egg", "cooking_oil", "chicken"]
    dates = pd.date_range("2024-01-01", periods=730)
    prices = [{"product": product, "date": day, "index": 1 + i * .0002 + .01 * np.sin(i / 20),
               "n_premises": 20, "synthetic": True} for product in products for i, day in enumerate(dates)]
    news = [{"article_id": f"FAKE-{i}", "title": f"FAKE {products[i % 4].replace('_', ' ')} supply story {i}",
             "summary": "Synthetic fixture summary", "body": "Synthetic fixture body", "source": "FAKE",
             "url": f"https://example.com/FAKE/{i}", "language": "en",
             "published_at": pd.Timestamp(dates[20 + i * 3], tz="Asia/Kuala_Lumpur"), "synthetic": True} for i in range(200)]
    examples = [{"article_id": news[i % 200]["article_id"], "product": products[(i // 200 + i) % 4],
                 "domain": "staple_food", "published_at": news[i % 200]["published_at"],
                 "text": article_text(news[i % 200]), "realized_return": [-.02, 0., .02][i % 3],
                 "momentum_return": [-.01, 0., .01][i % 3], "label": ["DOWN", "STABLE", "UP"][i % 3],
                 "synthetic": True} for i in range(500)]
    pd.DataFrame(prices).to_parquet(destination / "FAKE_price_index.parquet", index=False)
    pd.DataFrame(news).to_parquet(destination / "FAKE_news_clean.parquet", index=False)
    pd.DataFrame(examples).to_parquet(destination / "FAKE_examples.parquet", index=False)
    pd.DataFrame([{"product": product, "item_code": i, "synthetic": True} for i, product in enumerate(products)]).to_csv(destination / "FAKE_item_mapping.csv", index=False)


def seed_fixture_news(settings):
    if settings.data_mode != "fixture":
        raise AppError("Cannot seed fake news in real mode.", "Use explicit fixture mode and a FAKE database.")
    now = datetime.now(timezone.utc)
    store = ArticleStore(settings.sqlite_path)
    for row in read_data(settings, "news_clean.parquet").itertuples():
        store.insert(Article(row.url, row.title, row.source, now, row.summary, row.body, row.language, now))
