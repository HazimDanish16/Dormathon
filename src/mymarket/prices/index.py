"""Exact calendar-date price context from validated processed indexes only."""

from datetime import date, timedelta

from mymarket.config import Settings
from mymarket.contracts import read_data
from mymarket.errors import AppError


class PriceIndex:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.signature = None
        self.frame = None

    def load(self):
        path = self.settings.data_file("price_index.parquet")
        signature = (path.stat().st_mtime_ns, path.stat().st_size) if path.exists() else None
        if self.frame is None or signature != self.signature:
            self.frame = read_data(self.settings, "price_index.parquet")
            self.signature = signature
        return self.frame

    def value(self, product: str, day: date):
        frame = self.load()
        rows = frame[(frame["product"] == product) & (frame["date"] == day)]
        return float(rows.iloc[0]["index"]) if len(rows) else None

    def context(self, product: str, days: int = 90):
        if not 1 <= days <= 3650:
            raise AppError("Invalid price window.", "days must be 1..3650.")
        frame = self.load()
        rows = frame[frame["product"] == product].sort_values("date")
        if rows.empty:
            raise AppError("No price coverage for this product.", "Obtain a processed index covering the configured product.")
        latest = rows.iloc[-1]
        end = latest["date"]
        warnings = []
        changes = {}
        for horizon in [7, 30]:
            previous = self.value(product, end - timedelta(days=horizon))
            changes[f"change_{horizon}d_pct"] = (float(latest["index"]) / previous - 1) * 100 if previous else None
            if previous is None:
                warnings.append(f"Missing exact {horizon}-day comparison date.")
        tail = rows[rows["date"] >= end - timedelta(days=days - 1)]
        return {"product": product, "latest_index": float(latest["index"]), **changes,
                "series_tail": [{"date": row.date.isoformat(), "index": float(row.index), "n_premises": int(row.n_premises)} for row in tail.itertuples(index=False)],
                "data_as_of": end.isoformat(), "warnings": warnings}
