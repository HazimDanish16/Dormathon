"""Poll news, delegate price refresh, scan alerts, and score matured outcomes."""

import json
import logging
import sys

from mymarket.config import Settings
from mymarket.maintenance import daily_refresh

if __name__ == "__main__":
    logging.basicConfig(stream=sys.stderr, level=logging.INFO)
    try:
        settings = Settings.from_env()
        report = daily_refresh(settings)
        report_path = settings.project_root / "data" / "refresh" / "latest.json"
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    except Exception:
        logging.exception("Daily refresh could not start")
        report = {"status": "incomplete", "error": "Check configuration and database permissions."}
    print(json.dumps(report, indent=2))
    raise SystemExit(0 if report["status"] == "ok" else 1)
