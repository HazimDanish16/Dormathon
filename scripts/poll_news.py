"""Poll configured feeds once. Safe to schedule every few hours."""

import json
import logging
import sys

from mymarket.config import Settings
from mymarket.ingest.rss import poll_news


def main() -> int:
    logging.basicConfig(level=logging.INFO, stream=sys.stderr)
    try:
        settings = Settings.from_env()
        logging.getLogger().setLevel(settings.log_level)
        report = poll_news(settings)
    except Exception:
        logging.exception("News polling failed; check configuration and database permissions")
        return 1
    # This standalone CLI is not the MCP stdio process.
    print(json.dumps(report, indent=2))
    enabled = [source for source in report["sources"].values() if source["status"] != "disabled"]
    return 1 if not enabled or all(source["status"] == "error" for source in enabled) else 0


if __name__ == "__main__":
    raise SystemExit(main())
