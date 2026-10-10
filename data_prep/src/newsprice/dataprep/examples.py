"""Examples table for the app/modelling repo (Dormathon contract): one row per
(article, product) with the article text and two index returns. No UP/DOWN/STABLE
labels are produced here; thresholds belong to the training stage (train-only).

realized_return = I(d+H) / I(d-1) - 1      (H = 14)
momentum_return = I(d-1) / I(d-15) - 1
where d is the article's local (Kuala Lumpur) calendar date. Rows whose three
index endpoints are missing, or have fewer than `min_premises` premises, are dropped.
"""

from __future__ import annotations

import re

import pandas as pd

DOMAIN = "staple_food"
# Must stay identical to the app repo's config/products.yaml (aliases and excludes).
PRODUCTS = {
    "rice": {"aliases": ["rice", "beras", "padi"], "exclude": ["nasi lemak", "nasi goreng", "chicken rice shop"]},
    "egg": {"aliases": ["egg", "eggs", "telur"], "exclude": []},
    "cooking_oil": {"aliases": ["cooking oil", "vegetable oil", "palm cooking oil", "minyak masak"], "exclude": []},
    "chicken": {"aliases": ["chicken", "poultry", "broiler", "ayam"], "exclude": ["chicken rice shop", "ayam brand"]},
}  # bare "nasi" is deliberately not an alias (cooked rice)


def _pattern(phrases: list[str]) -> re.Pattern | None:
    if not phrases:
        return None
    alts = [r"\s+".join(re.escape(w) for w in p.split()) for p in phrases]
    return re.compile(r"(?<!\w)(?:" + "|".join(alts) + r")(?!\w)", re.IGNORECASE)


_COMPILED = {k: (_pattern(v["aliases"]), _pattern(v["exclude"])) for k, v in PRODUCTS.items()}


def match_products(text: str) -> list[str]:
    out = []
    for product, (alias, exclude) in _COMPILED.items():
        if alias.search(text) and not (exclude and exclude.search(text)):
            out.append(product)
    return out


def article_text(title: str, summary: str, body: str) -> str:
    return ". ".join([title, summary, body[:1500]])


def build_examples(
    news: pd.DataFrame,
    index: pd.DataFrame,
    horizon: int = 14,
    min_premises: int = 10,
) -> tuple[pd.DataFrame, dict]:
    """news: article_id,title,summary,body,published_at (tz-aware). index: product,date,index,n_premises."""
    local = news["published_at"].dt.tz_convert("Asia/Kuala_Lumpur")
    work = pd.DataFrame(
        {
            "article_id": news["article_id"].astype(str),
            "published_at": news["published_at"],
            "date": local.dt.tz_localize(None).dt.normalize(),
            "text": [article_text(t, s, b) for t, s, b in zip(news["title"], news["summary"], news["body"])],
        }
    )
    work["products"] = [match_products(t) for t in work["text"]]
    matched = work.explode("products").dropna(subset=["products"]).rename(columns={"products": "product"})
    stats = {"articles": int(len(work)), "article_product_matches": int(len(matched)), "per_product_matched": matched["product"].value_counts().to_dict()}

    idx = index.copy()
    idx["date"] = pd.to_datetime(idx["date"])
    lookup = idx.set_index(["product", "date"])[["index", "n_premises"]]

    def at(offset: int, name: str) -> pd.DataFrame:
        keys = pd.MultiIndex.from_arrays([matched["product"], matched["date"] + pd.Timedelta(days=offset)])
        got = lookup.reindex(keys)
        return pd.DataFrame({name: got["index"].to_numpy(), name + "_n": got["n_premises"].to_numpy()}, index=matched.index)

    ends = pd.concat([at(-1, "base"), at(horizon, "fut"), at(-15, "prev")], axis=1)
    m = pd.concat([matched, ends], axis=1)
    have = m[["base", "fut", "prev"]].notna().all(axis=1)
    enough = (m[["base_n", "fut_n", "prev_n"]] >= min_premises).all(axis=1)
    stats["dropped_missing_endpoint"] = int((~have).sum())
    stats["dropped_low_premises"] = int((have & ~enough).sum())
    m = m[have & enough].copy()
    m["realized_return"] = m["fut"] / m["base"] - 1.0
    m["momentum_return"] = m["base"] / m["prev"] - 1.0
    m["domain"] = DOMAIN
    out = m[["article_id", "product", "domain", "published_at", "text", "realized_return", "momentum_return"]]
    out = out.drop_duplicates(["article_id", "product"]).sort_values(["published_at", "article_id", "product"], ignore_index=True)
    stats["examples"] = int(len(out))
    stats["per_product"] = out["product"].value_counts().to_dict()
    stats["first"] = str(out["published_at"].min()) if len(out) else None
    stats["last"] = str(out["published_at"].max()) if len(out) else None
    stats["horizon_days"] = horizon
    stats["min_premises"] = min_premises
    return out, stats
