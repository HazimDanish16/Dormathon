"""Export real relevance candidates for human review, then assess labeled CSV."""

import argparse
import json
from pathlib import Path

from mymarket.config import Settings
from mymarket.errors import AppError
from mymarket.filter.audit import assess_audit, export_audit

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["export", "assess"])
    parser.add_argument("--file", type=Path, default=Path("data/audits/relevance.csv"))
    parser.add_argument("--size", type=int, default=120)
    parser.add_argument("--hours", type=int, default=8760)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--news-file", type=Path, help="Validate and sample the full historical news handoff instead of the live cache")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    if args.apply and args.action != "assess":
        parser.error("--apply is only valid with assess")
    if args.news_file and args.action != "export":
        parser.error("--news-file is only valid with export")
    try:
        settings = Settings.from_env()
        result = (export_audit(settings, args.file, args.size, args.hours, args.seed, args.news_file) if args.action == "export"
                  else assess_audit(settings, args.file, args.apply))
        print(json.dumps(result, indent=2))
    except AppError as exc:
        print(json.dumps(exc.payload(), indent=2))
        raise SystemExit(1)
