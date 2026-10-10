"""Exercise the actual stdio protocol and structured tool responses."""

import json
import os
import subprocess
import sys
from pathlib import Path

import anyio
import pytest
from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

from mymarket.config import Settings
from mymarket.mcp_server import create_server

ROOT = Path(__file__).resolve().parents[1]
TOOLS = {
    "list_domains", "fetch_news", "filter_relevant", "predict_impact",
    "price_context", "scan_alerts", "backtest_report", "forward_validation",
}


@pytest.mark.parametrize("entry_point", ["module", "console"])
def test_stdio_discovery_and_tool_calls(tmp_path, entry_point):
    async def exercise():
        params = StdioServerParameters(
            command=(sys.executable if entry_point == "module" else str(
                Path(sys.executable).with_name("mymarket.exe" if os.name == "nt" else "mymarket")
            )),
            args=["-m", "mymarket.mcp_server"] if entry_point == "module" else [],
            cwd=tmp_path,
            env={**os.environ, "MYMARKET_PROJECT_ROOT": str(ROOT), "MYMARKET_CONFIG_DIR": "config"},
        )
        with anyio.fail_after(30):
            async with stdio_client(params) as (read, write):
                async with ClientSession(read, write) as session:
                    initialized = await session.initialize()
                    assert initialized.serverInfo.name == "mymarket"
                    discovered = await session.list_tools()
                    assert {tool.name for tool in discovered.tools} == TOOLS
                    for name in TOOLS:
                        args = {"product": "chicken"} if name == "price_context" else {}
                        result = await session.call_tool(name, args)
                        assert not result.isError
                        payload = json.loads(result.content[0].text)
                        if name == "list_domains":
                            assert "chicken" in payload["domains"]["staple_food"]["products"]
                        else:
                            assert set(payload) == {"error", "hint"}
                            assert "not implemented" in payload["error"]

    anyio.run(exercise)


def test_invalid_startup_configuration_uses_stderr(tmp_path):
    result = subprocess.run(
        [sys.executable, "-m", "mymarket.mcp_server"],
        cwd=tmp_path,
        env={**os.environ, "MYMARKET_PROJECT_ROOT": str(tmp_path), "MYMARKET_CONFIG_DIR": "missing"},
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 2
    assert result.stdout == ""
    assert "Invalid configuration" in result.stderr


def test_missing_config_returns_json_error(tmp_path):
    async def exercise():
        server = create_server(Settings(tmp_path, tmp_path))
        result = await server.call_tool("list_domains", {})
        # FastMCP returns unstructured and structured content as a tuple.
        payload = json.loads(result[0][0].text)
        assert set(payload) == {"error", "hint"}
        assert "configuration" in payload["error"]

    anyio.run(exercise)
