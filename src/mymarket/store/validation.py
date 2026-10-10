"""Versioned prediction logging and idempotent exact-date outcome scoring."""

from datetime import date, datetime, timedelta, timezone

from mymarket.config import Settings
from mymarket.prices.index import PriceIndex
from mymarket.store.db import ArticleStore, KL, utc_stamp


class PredictionLedger:
    def __init__(self, settings: Settings):
        self.settings = settings

    def log(self, article: dict, prediction: dict, now: datetime | None = None):
        now = now or datetime.now(timezone.utc)
        article_day = datetime.fromisoformat(article["published_at"]).astimezone(KL).date()
        base = article_day - timedelta(days=1)
        target = article_day + timedelta(days=prediction["horizon_days"])
        eligible = not article.get("date_estimated", False) and now.astimezone(KL).date() < target
        store = ArticleStore(self.settings.sqlite_path)
        with store.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            exists = db.execute("""SELECT id FROM predictions WHERE article_id=? AND product=?
                                   AND model_version=? AND target_date=?""",
                                (article["id"], prediction["product"], prediction["model_version"], target.isoformat())).fetchone()
            if exists:
                return exists[0]
            return db.execute("""INSERT INTO predictions
                (article_id, product, direction, p_up, p_down, p_stable, model_version, created_at,
                 horizon_days, threshold, base_date, target_date, abstained, synthetic, eligible)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (article["id"], prediction["product"], prediction["direction"], prediction["probs"]["UP"],
                 prediction["probs"]["DOWN"], prediction["probs"]["STABLE"], prediction["model_version"],
                 utc_stamp(now), prediction["horizon_days"], prediction["thresholds"][prediction["product"]],
                 base.isoformat(), target.isoformat(), prediction["abstained"], self.settings.data_mode == "fixture", eligible)).lastrowid

    def score(self, now: datetime | None = None):
        now = now or datetime.now(timezone.utc)
        today = now.astimezone(KL).date().isoformat()
        store = ArticleStore(self.settings.sqlite_path)
        with store.connection() as db:
            rows = db.execute("""SELECT p.* FROM predictions p LEFT JOIN outcomes o ON p.id=o.prediction_id
                 WHERE o.prediction_id IS NULL AND p.target_date<=? AND p.eligible=1 AND p.abstained=0 AND p.synthetic=?""",
                 (today, self.settings.data_mode == "fixture")).fetchall()
        prices = PriceIndex(self.settings)
        scored, missing = 0, 0
        for row in rows:
            base = prices.value(row["product"], date.fromisoformat(row["base_date"]))
            future = prices.value(row["product"], date.fromisoformat(row["target_date"]))
            if base is None or future is None:
                missing += 1
                continue
            realized = future / base - 1
            label = "UP" if realized > row["threshold"] else "DOWN" if realized < -row["threshold"] else "STABLE"
            with store.connection() as db:
                result = db.execute("INSERT OR IGNORE INTO outcomes VALUES (?, ?, ?, ?)",
                                    (row["id"], realized, label, utc_stamp(now)))
                scored += result.rowcount
        return {"scored": scored, "missing_price_windows": missing}

    def report(self, product=None):
        store = ArticleStore(self.settings.sqlite_path)
        condition = "p.synthetic=?"
        params = [self.settings.data_mode == "fixture"]
        if product is not None:
            condition += " AND p.product=?"
            params.append(product)
        with store.connection() as db:
            rows = db.execute(f"""SELECT p.*, o.realized_label FROM predictions p LEFT JOIN outcomes o ON p.id=o.prediction_id
                                    WHERE {condition}""", params).fetchall()
        scored = [row for row in rows if row["realized_label"] is not None and row["eligible"] and not row["abstained"]]
        groups = {}
        for row in scored:
            group = groups.setdefault(row["model_version"], {"scored": 0, "correct": 0})
            group["scored"] += 1
            group["correct"] += row["direction"] == row["realized_label"]
        for group in groups.values():
            group["accuracy"] = group["correct"] / group["scored"]
        return {"product": product, "logged": len(rows), "scored": len(scored),
                "pending": sum(row["eligible"] and not row["abstained"] and row["realized_label"] is None for row in rows),
                "excluded": sum(not row["eligible"] or row["abstained"] for row in rows),
                "accuracy": sum(row["direction"] == row["realized_label"] for row in scored) / len(scored) if scored else None,
                "per_model": groups, "message": "No matured scored predictions yet." if not scored else "Computed from logged predictions and observed price windows."}
