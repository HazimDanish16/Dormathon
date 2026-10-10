"""Runtime settings, read from environment variables (see .env.example)."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _load_dotenv(path: Path = Path(".env")) -> None:
    """Minimal .env loader so we don't need python-dotenv. Existing env wins."""
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())


@dataclass(frozen=True)
class Settings:
    data_dir: Path
    horizon_days: int
    flat_band: float
    alert_min_prob: float
    llm_model: str
    anthropic_api_key: str | None
    mcp_auth_token: str | None
    mcp_host: str
    mcp_port: int

    @property
    def prices_dir(self) -> Path:
        return self.data_dir / "prices"

    @property
    def model_path(self) -> Path:
        return self.data_dir / "model" / "impact_model.joblib"

    @property
    def metrics_path(self) -> Path:
        return self.data_dir / "model" / "metrics.json"

    @property
    def digest_dir(self) -> Path:
        return self.data_dir / "digest"

    @property
    def prediction_log(self) -> Path:
        return self.data_dir / "predictions.jsonl"

    @property
    def daily_prices_path(self) -> Path:
        return self.prices_dir / "daily_national_median.parquet"

    @property
    def item_lookup_path(self) -> Path:
        return self.prices_dir / "lookup_item.parquet"


def get_settings() -> Settings:
    _load_dotenv()
    return Settings(
        data_dir=Path(os.environ.get("NEWSPRICE_DATA_DIR", "./data")).resolve(),
        horizon_days=int(os.environ.get("NEWSPRICE_HORIZON_DAYS", "14")),
        flat_band=float(os.environ.get("NEWSPRICE_FLAT_BAND", "0.02")),
        alert_min_prob=float(os.environ.get("NEWSPRICE_ALERT_MIN_PROB", "0.6")),
        llm_model=os.environ.get("NEWSPRICE_LLM_MODEL", "claude-opus-5-5"),
        anthropic_api_key=os.environ.get("ANTHROPIC_API_KEY") or None,
        mcp_auth_token=os.environ.get("MCP_AUTH_TOKEN") or None,
        mcp_host=os.environ.get("MCP_HOST", "127.0.0.1"),
        mcp_port=int(os.environ.get("MCP_PORT", "8000")),
    )
