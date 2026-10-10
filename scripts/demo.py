"""Offline fixture demonstration. Uses synthetic test doubles, not trained models."""

import argparse
import json
from pathlib import Path

from mymarket.config import Settings
from mymarket.service import MarketService
from mymarket.fixtures import generate, seed_fixture_news


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=Path(".tools/FAKE-demo"))
    directory = parser.parse_args().output.resolve()
    generate(directory)
    root = Path(__file__).resolve().parents[1]
    settings = Settings(root, root / "config", database_path=directory / "FAKE.sqlite3", data_mode="fixture", data_dir=directory)
    seed_fixture_news(settings)
    service = MarketService(settings)
    result = service.scan_alerts()
    print(json.dumps({"synthetic": True, "message": "FAKE test doubles, no real model accuracy.",
                      "alerts": len(result["alerts"]), "sample": result["alerts"][:1],
                      "backtest": service.backtest_report(), "forward": service.forward_validation()}, indent=2))
