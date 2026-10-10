"""All eight tools perform app behavior over stdio using explicit FAKE inputs."""

import json
import os
import sys
from pathlib import Path

import anyio
from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

from mymarket.config import Settings
from mymarket.fixtures import generate, seed_fixture_news

ROOT = Path(__file__).resolve().parents[1]


def test_all_eight_tools_with_fixture_test_doubles(tmp_path):
    generate(tmp_path)
    settings = Settings(ROOT, ROOT / "config", data_mode="fixture", data_dir=tmp_path, database_path=tmp_path / "FAKE.sqlite3")
    seed_fixture_news(settings)
    calls = {"list_domains": {}, "fetch_news": {"limit": 4}, "filter_relevant": {},
             "predict_impact": {"text": "Chicken shortage", "products": ["chicken"]}, "price_context": {"product": "chicken"},
             "scan_alerts": {"min_confidence": .7}, "backtest_report": {}, "forward_validation": {}}
    async def exercise():
        params = StdioServerParameters(command=sys.executable, args=["-m", "mymarket.mcp_server"], cwd=tmp_path,
                                      env={**os.environ, "MYMARKET_PROJECT_ROOT": str(ROOT), "MYMARKET_CONFIG_DIR": "config",
                                           "MYMARKET_DATA_MODE": "fixture", "MYMARKET_DATA_DIR": str(tmp_path), "MYMARKET_DATABASE_PATH": str(settings.sqlite_path)})
        with anyio.fail_after(40):
            async with stdio_client(params) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    for name, args in calls.items():
                        result = await session.call_tool(name, args)
                        assert not result.isError
                        payload = json.loads(result.content[0].text)
                        assert "error" not in payload, (name, payload)
                        assert payload["synthetic"] is True
                        if name == "scan_alerts":
                            assert payload["alerts"]
                        if name == "backtest_report":
                            assert payload["metrics"] is None
                    invalid = await session.call_tool("fetch_news", {"hours": "invalid"})
                    assert set(json.loads(invalid.content[0].text)) == {"error", "hint"}
    anyio.run(exercise)
