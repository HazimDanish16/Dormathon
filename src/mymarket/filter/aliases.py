"""Configuration-driven bilingual word-boundary matching."""

import re

from mymarket.config import ProductsConfig


def article_text(article: dict) -> str:
    return ". ".join([article.get("title", ""), article.get("summary", ""), article.get("body", "")[:1500]])


def product_description(product_id: str, product) -> str:
    return product.description or (f"Price and supply of {product_id.replace('_', ' ')} in Malaysia. "
                                   + ", ".join(product.aliases_en + product.aliases_ms))


def contains(text: str, phrase: str) -> bool:
    pattern = r"(?<!\w)" + r"\s+".join(re.escape(word) for word in phrase.split()) + r"(?!\w)"
    return bool(re.search(pattern, text, re.IGNORECASE)) if phrase.strip() else False


def match_aliases(text: str, config: ProductsConfig, domain: str | None = None) -> list[dict]:
    results = []
    for domain_id, group in config.domains.items():
        if domain is not None and domain != domain_id:
            continue
        for product_id, product in group.products.items():
            # Bare "nasi" means cooked rice and is too ambiguous for raw-rice supply.
            aliases = [alias for alias in product.aliases_en + product.aliases_ms if alias.casefold() != "nasi"]
            terms = [alias for alias in aliases if contains(text, alias)]
            if terms and not any(contains(text, phrase) for phrase in product.exclude_phrases):
                results.append({"product": product_id, "domain": domain_id, "matched_terms": terms})
    return results
