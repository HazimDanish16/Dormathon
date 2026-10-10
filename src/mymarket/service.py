"""Application services shared by MCP and maintenance commands."""

import json

import numpy as np

from mymarket.config import Settings, load_products
from mymarket.errors import AppError
from mymarket.filter.aliases import article_text, match_aliases
from mymarket.filter.embed_filter import Embedder, filter_threshold
from mymarket.store.db import ArticleStore


class MarketService:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.config = load_products(settings)
        self.embedder = Embedder(settings)

    @property
    def synthetic(self) -> bool:
        return self.settings.data_mode == "fixture"

    def response(self, **values) -> dict:
        return {**values, "synthetic": self.synthetic}

    def validate_domain(self, domain):
        if domain is not None and domain not in self.config.domains:
            raise AppError("Unknown domain.", "Use a domain returned by list_domains.")

    def product_domain(self, product):
        for domain_id, domain in self.config.domains.items():
            if product in domain.products:
                return domain_id
        raise AppError("Unknown product.", "Use a product returned by list_domains.")

    def filter_relevant(self, domain=None, hours=48, deadline=None):
        self.validate_domain(domain)
        if not 1 <= hours <= 8760:
            raise AppError("Invalid news window.", "hours must be 1..8760.")
        store = ArticleStore(self.settings.sqlite_path)
        articles = store.recent(hours=hours, limit=1000, include_body=True)
        candidates = []
        texts = []
        for article in articles:
            text = article_text(article)
            for match in match_aliases(text, self.config, domain):
                product = self.config.domains[match["domain"]].products[match["product"]]
                description = product.description or f"Price and supply of {match['product'].replace('_', ' ')} in Malaysia. " + ", ".join(product.aliases_en + product.aliases_ms)
                candidates.append((article, match))
                texts.extend(["query: " + text, "passage: " + description])
        threshold, audited = filter_threshold(self.settings)
        matches = []
        if texts:
            vectors = self.embedder.encode(texts)
            with store.connection() as db:
                for i, (article, match) in enumerate(candidates):
                    score = float(np.dot(vectors[2 * i], vectors[2 * i + 1]))
                    if score >= threshold:
                        matches.append({"article": article, **match, "match_score": score})
                        db.execute("INSERT OR REPLACE INTO article_products VALUES (?, ?, ?, ?)",
                                   (article["id"], match["product"], score, json.dumps(match["matched_terms"])))
                    else:
                        db.execute("DELETE FROM article_products WHERE article_id=? AND product=?", (article["id"], match["product"]))
        return self.response(matches=matches, count=len(matches), threshold=threshold,
                             threshold_audited=audited, warnings=[] if audited else ["Relevance threshold is untuned."])
