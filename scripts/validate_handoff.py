"""Validate teammate data and perform an actual CPU probability prediction."""

import json

from mymarket.config import Settings
from mymarket.errors import AppError
from mymarket.maintenance import validate_handoff

if __name__ == "__main__":
    try:
        print(json.dumps(validate_handoff(Settings.from_env()), indent=2))
    except AppError as exc:
        print(json.dumps({"ready": False, **exc.payload()}, indent=2))
        raise SystemExit(1)
