"""Audit integrity, human-label requirements, and threshold holdout behavior."""

import csv
from pathlib import Path

import numpy as np
import pytest

from mymarket.config import Settings
from mymarket.errors import AppError
from mymarket.filter.audit import FIELDS, assess_audit, export_audit
from mymarket.filter.embed_filter import Embedder, filter_threshold
from mymarket.store.db import ArticleStore, utc_stamp
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[1]


def setup_audit(tmp_path, monkeypatch, count=160, mode="real"):
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "products.yaml").write_bytes((ROOT / "config/products.yaml").read_bytes())
    settings = Settings(tmp_path, config_dir, database_path=tmp_path / "FAKE.sqlite3", data_mode=mode)
    store = ArticleStore(settings.sqlite_path)
    now = utc_stamp(datetime.now(timezone.utc))
    with store.connection() as db:
        for i in range(count):
            product = ["Chicken", "Rice", "Egg", "Cooking oil"][i % 4]
            db.execute("""INSERT INTO articles (url,title,source,published_at,summary,body,lang,fetched_at)
                          VALUES (?,?,'test',?,'','','en',?)""", (f"https://example.com/{i}", f"{product} supply {i}", now, now))
    monkeypatch.setattr(Embedder, "encode", lambda self, texts: np.tile([1., 0.], (len(texts), 1)))
    return settings, tmp_path / "audit.csv"


def label(path, value="1"):
    with path.open(encoding="utf-8-sig", newline="") as source:
        rows = list(csv.DictReader(source))
    for row in rows:
        row["relevant"] = value
    with path.open("w", encoding="utf-8-sig", newline="") as output:
        writer = csv.DictWriter(output, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    return rows


def test_export_below_threshold_preserves_labels_and_grouping(tmp_path, monkeypatch):
    settings, path = setup_audit(tmp_path, monkeypatch, count=5)
    monkeypatch.setattr(Embedder, "encode", lambda self, texts: np.array([[1., 0.], [0., 1.]] * (len(texts)//2)))
    metadata = export_audit(settings, path)
    assert metadata["sampled"] == 5
    assert metadata["requested"] == 120
    with path.open(encoding="utf-8-sig", newline="") as source:
        rows = list(csv.DictReader(source))
    assert all(row["relevant"] == "" and row["similarity"] == "0.0" for row in rows)
    with pytest.raises(AppError, match="already exists"):
        export_audit(settings, path)
    with pytest.raises(AppError, match="incomplete"):
        assess_audit(settings, path)


def test_apply_requires_real_sufficient_holdout_and_tracks_provenance(tmp_path, monkeypatch):
    settings, path = setup_audit(tmp_path, monkeypatch)
    export_audit(settings, path)
    label(path)
    report = assess_audit(settings, path, apply=True)
    assert report["ready_to_apply"]
    assert report["validation"]["precision"] == 1
    assert report["validation"]["precision_ci95_wilson"][0] < 1
    assert filter_threshold(settings) == (0., True)
    products = settings.config_dir / "products.yaml"
    products.write_text(products.read_text() + "\n# Changed alias configuration\n")
    assert filter_threshold(settings) == (.8, False)
    with pytest.raises(AppError, match="invalid"):
        assess_audit(settings, path)


@pytest.mark.parametrize("mode,count", [("fixture", 160), ("real", 5)])
def test_small_or_synthetic_audits_cannot_apply(tmp_path, monkeypatch, mode, count):
    settings, path = setup_audit(tmp_path, monkeypatch, count=count, mode=mode)
    export_audit(settings, path)
    label(path)
    assert not assess_audit(settings, path)["ready_to_apply"]
    with pytest.raises(AppError, match="insufficient"):
        assess_audit(settings, path, apply=True)
    assert not (settings.config_dir / "filter_threshold.json").exists()


def test_tampered_scores_and_invalid_labels_are_rejected(tmp_path, monkeypatch):
    settings, path = setup_audit(tmp_path, monkeypatch)
    export_audit(settings, path)
    label(path, value="maybe")
    with pytest.raises(AppError, match="invalid"):
        assess_audit(settings, path)
    label(path)
    text = path.read_text(encoding="utf-8-sig").replace(",1.0,", ",0.1,")
    path.write_text(text, encoding="utf-8-sig")
    with pytest.raises(AppError, match="invalid"):
        assess_audit(settings, path)


def test_holdout_failure_does_not_reselect_threshold(tmp_path, monkeypatch):
    settings, path = setup_audit(tmp_path, monkeypatch)
    export_audit(settings, path)
    rows = label(path)
    for row in rows:
        if row["split"] == "validation":
            row["relevant"] = "0"
    with path.open("w", encoding="utf-8-sig", newline="") as output:
        writer = csv.DictWriter(output, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    report = assess_audit(settings, path)
    assert report["recommended_threshold"] == 0.
    assert report["validation"]["precision"] == 0.
    assert not report["ready_to_apply"]
