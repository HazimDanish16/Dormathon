"""Generate deterministic synthetic handoff data. Never used as real data."""

import argparse
from pathlib import Path

import numpy as np
import pandas as pd


def generate(destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    products = ["rice", "egg", "cooking_oil", "chicken"]
    dates = pd.date_range("2024-01-01", periods=730)
    prices = [{"product": product, "date": date, "index": 1 + day * .0002 + .01 * np.sin(day / 20),
               "n_premises": 20, "synthetic": True} for product in products for day, date in enumerate(dates)]
    news = [{"article_id": f"FAKE-{i}", "title": f"FAKE {products[i % 4].replace('_', ' ')} supply story {i}",
             "summary": "Synthetic fixture summary", "body": "Synthetic fixture body", "source": "FAKE",
             "url": f"https://example.com/FAKE/{i}", "language": "en",
             "published_at": pd.Timestamp(dates[20 + i * 3], tz="Asia/Kuala_Lumpur"), "synthetic": True} for i in range(200)]
    examples = [{"article_id": news[i % 200]["article_id"], "product": products[(i // 200 + i) % 4],
                 "domain": "staple_food", "published_at": news[i % 200]["published_at"],
                 "text": news[i % 200]["title"], "realized_return": [-.02, 0., .02][i % 3],
                 "momentum_return": [-.01, 0., .01][i % 3], "label": ["DOWN", "STABLE", "UP"][i % 3],
                 "synthetic": True} for i in range(500)]
    pd.DataFrame(prices).to_parquet(destination / "FAKE_price_index.parquet", index=False)
    pd.DataFrame(news).to_parquet(destination / "FAKE_news_clean.parquet", index=False)
    pd.DataFrame(examples).to_parquet(destination / "FAKE_examples.parquet", index=False)
    pd.DataFrame([{"product": product, "item_code": i, "synthetic": True} for i, product in enumerate(products)]).to_csv(destination / "FAKE_item_mapping.csv", index=False)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=Path("tests/fixtures"))
    generate(parser.parse_args().output)
    print("FAKE fixtures generated. These are synthetic, not training data.")
