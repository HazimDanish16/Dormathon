"""Application services shared by MCP and maintenance commands."""

import json
import time

import numpy as np

from mymarket.config import Settings, load_products
from mymarket.errors import AppError
from mymarket.filter.aliases import article_text, match_aliases
from mymarket.filter.embed_filter import Embedder, filter_threshold
from mymarket.store.db import ArticleStore
from mymarket.model.predict import Predictor
from mymarket.prices.index import PriceIndex
from mymarket.llm.explain import Explainer
from mymarket.store.validation import PredictionLedger


class MarketService:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.config = load_products(settings)
        self.embedder = Embedder(settings)
        self.predictor = Predictor(settings)
        self.prices = PriceIndex(settings)
        self.explainer = Explainer(settings)
        self.ledger = PredictionLedger(settings)

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
            vectors = self.embedder.encode(texts, deadline=deadline) if deadline is not None else self.embedder.encode(texts)
            for i, (article, match) in enumerate(candidates):
                score = float(np.dot(vectors[2 * i], vectors[2 * i + 1]))
                if score >= threshold:
                    matches.append({"article": article, **match, "match_score": score})
        products = [product for domain_id, configured in self.config.domains.items()
                    if domain is None or domain_id == domain for product in configured.products]
        with store.connection() as db:
            # Replace the evaluated scope even when aliases now produce no candidates.
            db.executemany("DELETE FROM article_products WHERE article_id=? AND product=?",
                           [(article["id"], product) for article in articles for product in products])
            db.executemany("INSERT INTO article_products VALUES (?, ?, ?, ?)",
                           [(match["article"]["id"], match["product"], match["match_score"],
                             json.dumps(match["matched_terms"])) for match in matches])
        return self.response(matches=matches, count=len(matches), threshold=threshold,
                             threshold_audited=audited, warnings=[] if audited else ["Relevance threshold is untuned."])

    def predict_impact(self, url=None, text=None, products=None):
        if bool(url) == bool(text):
            raise AppError("Provide exactly one of url or text.", "Supply article text, or the URL of a cached article.")
        article = None
        if url:
            from mymarket.store.db import canonical_url
            with ArticleStore(self.settings.sqlite_path).connection() as db:
                row = db.execute("SELECT * FROM articles WHERE url=?", (canonical_url(url),)).fetchone()
            if row is None:
                raise AppError("Article URL is not cached.", "Run the news poller first or supply text; this tool does not fetch arbitrary URLs.")
            text = article_text(dict(row))
            article = dict(row)
        if not isinstance(text, str) or not text.strip() or len(text) > 20000:
            raise AppError("Invalid article text.", "Supply nonempty text up to 20,000 characters.")
        if products is None:
            products = [match["product"] for match in match_aliases(text, self.config)]
        selected = [(product, self.product_domain(product)) for product in dict.fromkeys(products)]
        if not selected:
            return self.response(predictions=[], warnings=["No tracked product aliases matched."])
        predictions = self.predictor.predict(text, selected)
        article = article or ArticleStore(self.settings.sqlite_path).record_text(text)
        for prediction in predictions:
            prediction["prediction_id"] = self.ledger.log(article, prediction)
        return self.response(predictions=predictions)

    def price_context(self, product, days=90):
        self.product_domain(product)
        return self.response(**self.prices.context(product, days))

    def backtest_report(self, product=None):
        if product is not None:
            self.product_domain(product)
        if self.synthetic:
            return self.response(available=False, metrics=None, message="FAKE test doubles have no model accuracy. Obtain the real Colab evaluation export.")
        bundle = self.predictor.bundle.load()
        metrics = bundle.metrics
        if product is not None:
            if product not in metrics.get("by_product", {}):
                raise AppError("No computed metrics for this product.", "Ask your teammate to include by_product results; aggregate metrics are not a substitute.")
            metrics = {"product": product, "results": metrics["by_product"][product],
                       "model_version": bundle.manifest.model_version, "dataset_provenance": metrics["dataset_provenance"]}
        return self.response(available=True, metrics=metrics)

    def scan_alerts(self, domain=None, hours=48, min_confidence=.55, lang="en"):
        self.validate_domain(domain)
        if lang not in {"en", "ms"} or not 0 <= min_confidence <= 1:
            raise AppError("Invalid alert options.", "Use lang=en or ms and min_confidence=0..1.")
        started = time.monotonic()
        filtered = self.filter_relevant(domain, hours, deadline=started + 50)
        alerts, warnings = [], list(filtered["warnings"])
        deadline = min(started + 50, time.monotonic() + 30)
        candidates = filtered["matches"][:100]
        if len(filtered["matches"]) > 100:
            warnings.append("Alert processing limited to the newest 100 article/product matches.")
        for match in candidates:
            if time.monotonic() >= started + 50:
                warnings.append("Alert time budget reached; remaining matches were deferred.")
                break
            article = match["article"]
            prediction = self.predictor.predict(article_text(article), [(match["product"], match["domain"])], min_confidence)[0]
            self.ledger.log(article, prediction)
            if prediction["abstained"]:
                continue
            context = self.prices.context(match["product"], days=30)
            facts = {"article": {key: article[key] for key in ["title", "source", "published_at", "url"]},
                     "prediction": {key: prediction[key] for key in ["product", "direction", "confidence", "probs", "triggers"]},
                     "price_context": {key: context[key] for key in ["latest_index", "change_7d_pct", "change_30d_pct", "data_as_of"]}}
            explanation = self.explainer.explain(facts, lang, deadline=deadline)
            alerts.append({"article": facts["article"], **prediction, "price_context": context,
                           "explanation": explanation, "synthetic": self.synthetic})
        summary = "Tiada amaran yang memenuhi tahap keyakinan." if lang == "ms" else "No alerts met the confidence threshold."
        if alerts:
            summary = f"{len(alerts)} amaran untuk semakan." if lang == "ms" else f"{len(alerts)} alerts for review."
        return self.response(alerts=alerts, domain_summary=summary, warnings=warnings)

    def forward_validation(self, product=None):
        if product is not None:
            self.product_domain(product)
        return self.response(**self.ledger.report(product))
