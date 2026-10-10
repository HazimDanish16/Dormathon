"""Human relevance audit snapshots and grouped holdout threshold assessment."""

import csv
import hashlib
import json
import math
import random
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from mymarket.config import load_products
from mymarket.contracts import validate_frame
from mymarket.errors import AppError
from mymarket.filter.aliases import article_text, match_aliases, product_description
from mymarket.filter.embed_filter import Embedder
from mymarket.store.db import ArticleStore, canonical_url

FIELDS = ["article_id", "product", "domain", "source", "published_at", "url", "title",
          "text", "matched_terms", "similarity", "split", "relevant", "notes"]


def config_hash(settings):
    return hashlib.sha256((settings.config_dir / "products.yaml").read_bytes()).hexdigest()


def snapshot_hash(rows):
    values = [{key: row[key] for key in FIELDS if key not in {"relevant", "notes"}} for row in rows]
    return hashlib.sha256(json.dumps(values, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def historical_articles(settings, path, provenance):
    """Validate the complete handoff in bounded batches, including global uniqueness."""
    import pyarrow.parquet as pq
    seen_ids, seen_urls = set(), set()
    try:
        archive = pq.ParquetFile(path)
        provenance.update(rows=archive.metadata.num_rows, sources={}, date_min=None, date_max=None)
        for batch in archive.iter_batches(batch_size=1024):
            frame = validate_frame(batch.to_pandas(), "news_clean.parquet", settings)
            for row in frame.to_dict("records"):
                article_id, url = row["article_id"], canonical_url(row["url"])
                if article_id in seen_ids or url in seen_urls:
                    raise ValueError("Duplicate article IDs or canonical URLs across archive batches")
                seen_ids.add(article_id)
                seen_urls.add(url)
                stamp = row["published_at"].isoformat()
                provenance["date_min"] = min(provenance["date_min"] or stamp, stamp)
                provenance["date_max"] = max(provenance["date_max"] or stamp, stamp)
                source = row["source"]
                provenance["sources"][source] = provenance["sources"].get(source, 0) + 1
                yield {**row, "id": article_id, "published_at": stamp}
        if not seen_ids:
            raise ValueError("News archive is empty")
    except (ValueError, OSError, KeyError) as exc:
        raise AppError("Historical news violates the handoff contract.", str(exc)) from exc


def export_audit(settings, path: Path, size=120, hours=8760, seed=42, news_file: Path | None = None):
    if path.exists() or path.with_suffix(".json").exists():
        raise AppError("Audit output already exists.", "Use a new filename to preserve existing human labels.")
    if not 1 <= size <= 1000 or not 1 <= hours <= 8760:
        raise AppError("Invalid audit window or size.", "Use size=1..1000 and hours=1..8760; aim for at least 120 labeled pairs.")
    config = load_products(settings)
    rng = random.Random(seed)
    provenance = {}
    pool_products = Counter()
    if news_file is not None:
        news_file = news_file.resolve()
        if not news_file.is_file():
            raise AppError("Historical news file is missing.", "Provide an existing news_clean.parquet handoff with --news-file.")
        original_stat = news_file.stat()
        # Reservoir sampling is uniform over all pairs, without retaining the archive.
        selected, count, matched_articles = [], 0, 0
        for article in historical_articles(settings, news_file, provenance):
            matches = match_aliases(article_text(article), config)
            matched_articles += bool(matches)
            for match in matches:
                count += 1
                pool_products[match["product"]] += 1
                candidate = (article, match)
                if len(selected) < size:
                    selected.append(candidate)
                else:
                    index = rng.randrange(count)
                    if index < size:
                        selected[index] = candidate
        current_stat = news_file.stat()
        if (original_stat.st_size, original_stat.st_mtime_ns) != (current_stat.st_size, current_stat.st_mtime_ns):
            raise AppError("News archive changed during validation.", "Wait for the file transfer to finish, then export again.")
        digest = hashlib.sha256()
        with news_file.open("rb") as source:
            for block in iter(lambda: source.read(1024*1024), b""):
                digest.update(block)
        provenance.update(kind="historical_handoff", filename=news_file.name, sha256=digest.hexdigest(),
                          matched_articles=matched_articles, candidate_products=dict(pool_products))
        scope = "Uniform reservoir sample of alias candidates across the entire validated news handoff; cannot measure alias recall."
    else:
        articles = ArticleStore(settings.sqlite_path).recent(hours=hours, limit=1000, include_body=True)
        candidates = [(article, match) for article in articles for match in match_aliases(article_text(article), config)]
        count = len(candidates)
        selected = rng.sample(candidates, min(size, count))
        provenance = {"kind": "live_cache", "rows": len(articles)}
        scope = "Random sample of alias candidates in the newest 1000 cached articles; cannot measure alias recall."
    if not count:
        raise AppError("No alias-matched news is available.", "Poll real news, or widen the news window; no fake rows will be substituted.")
    ids = sorted({article["id"] for article, _ in selected})
    rng.shuffle(ids)
    holdout = set(ids[:max(1, math.ceil(len(ids) * .3))])
    texts = []
    for article, match in selected:
        product = config.domains[match["domain"]].products[match["product"]]
        texts.extend(["query: " + article_text(article), "passage: " + product_description(match["product"], product)])
    vectors = Embedder(settings).encode(texts)
    rows = []
    for i, (article, match) in enumerate(selected):
        rows.append({"article_id": str(article["id"]), "product": match["product"], "domain": match["domain"],
                     "source": article["source"], "published_at": article["published_at"], "url": article["url"],
                     "title": article["title"], "text": article_text(article), "matched_terms": ", ".join(match["matched_terms"]),
                     "similarity": str(float(np.clip(np.dot(vectors[2*i], vectors[2*i+1]), -1, 1))),
                     "split": "validation" if article["id"] in holdout else "tuning", "relevant": "", "notes": ""})
    metadata = {"schema_version": 1, "created_at": datetime.now(timezone.utc).isoformat(),
                "synthetic": settings.data_mode == "fixture", "embedding_key": Embedder(settings).key,
                "config_sha256": config_hash(settings), "snapshot_sha256": snapshot_hash(rows),
                "seed": seed, "hours": hours if news_file is None else None, "requested": size, "candidates": count, "sampled": len(rows),
                "input": provenance,
                "products": dict(Counter(row["product"] for row in rows)),
                "limitations": [scope,
                                "Holdout groups article IDs; related stories may still be correlated.",
                                "Precision estimates do not establish model prediction accuracy."]}
    if len(rows) < size:
        metadata["limitations"].append("Input has too few candidates for the requested sample; collect more real news.")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8-sig", newline="") as output:
        writer = csv.DictWriter(output, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    path.with_suffix(".json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    return metadata


def stats(rows, threshold):
    accepted = [row for row in rows if float(row["similarity"]) >= threshold]
    correct = sum(int(row["relevant"]) for row in accepted)
    n = len(accepted)
    precision = correct / n if n else None
    interval = None
    if n:
        z = 1.96
        centre = (precision + z*z/(2*n)) / (1+z*z/n)
        half = z * math.sqrt(precision*(1-precision)/n + z*z/(4*n*n)) / (1+z*z/n)
        interval = [centre-half, centre+half]
    return {"labeled": len(rows), "accepted": n, "relevant_accepted": correct,
            "precision": precision, "precision_ci95_wilson": interval}


def assess_audit(settings, path: Path, apply=False):
    try:
        metadata = json.loads(path.with_suffix(".json").read_text(encoding="utf-8"))
        with path.open(encoding="utf-8-sig", newline="") as source:
            rows = list(csv.DictReader(source))
        if not rows or snapshot_hash(rows) != metadata["snapshot_sha256"]:
            raise ValueError("Audit snapshot changed")
        if metadata["config_sha256"] != config_hash(settings) or metadata["embedding_key"] != Embedder(settings).key:
            raise ValueError("Configuration or embedding revision changed; export a new audit")
        if any(row["relevant"].strip() not in {"0", "1"} for row in rows):
            raise ValueError("Label every relevant cell with 0 or 1")
        if any(not math.isfinite(float(row["similarity"])) or not -1 <= float(row["similarity"]) <= 1 for row in rows):
            raise ValueError("Invalid similarity")
    except (ValueError, KeyError, OSError) as exc:
        raise AppError("Audit is incomplete or invalid.", str(exc)) from exc
    tuning = [row for row in rows if row["split"] == "tuning"]
    validation = [row for row in rows if row["split"] == "validation"]
    choices = []
    for threshold in sorted({0., .8, *(float(row["similarity"]) for row in tuning if float(row["similarity"]) >= 0)}):
        result = stats(tuning, threshold)
        if result["accepted"] >= 20 and result["precision"] >= .8:
            choices.append((threshold, result))
    choice = max(choices, key=lambda pair: (pair[1]["accepted"], -pair[0])) if choices else None
    threshold = choice[0] if choice else None
    held = stats(validation, threshold) if choice else None
    configured = {product for group in load_products(settings).domains.values() for product in group.products}
    per_product = {product: stats([row for row in validation if row["product"] == product], threshold)
                   for product in sorted(configured)} if choice else {}
    covered = bool(per_product and all(result["accepted"] >= 5 and result["precision"] >= .8 for result in per_product.values()))
    ready = bool(not metadata["synthetic"] and len(rows) >= 120 and held and held["accepted"] >= 20 and held["precision"] >= .8 and covered)
    report = {"synthetic": metadata["synthetic"], "recommended_threshold": threshold, "ready_to_apply": ready,
              "default_0_80": stats(rows, .8), "tuning": choice[1] if choice else None, "validation": held,
              "per_product_validation": per_product,
              "limitations": metadata["limitations"] + ["Threshold selected on tuning rows only; validation precision is a point estimate, not a guaranteed 80% lower bound."]}
    if not ready:
        report["limitations"].append("Applying requires 120 real labeled pairs, 20 accepted tuning/holdout pairs with precision >=80%, and 5 accepted holdout pairs per configured product with precision >=80%.")
    if apply:
        if not ready:
            raise AppError("Audit is insufficient to apply a threshold.", "Collect more independent real news or improve exclusions and export a fresh audit; inspect the assessment without --apply.")
        destination = settings.config_dir / "filter_threshold.json"
        destination.write_text(json.dumps({"threshold": threshold, "audited": True,
                                          "embedding_key": metadata["embedding_key"], "config_sha256": metadata["config_sha256"],
                                          "audit": metadata, "assessment": report}, indent=2), encoding="utf-8")
    return report
