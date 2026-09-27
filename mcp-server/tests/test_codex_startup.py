"""Exercise the Codex launch declaration from a relocated plugin package."""

from __future__ import annotations

import asyncio
import importlib.util
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import unittest


HAS_MCP = importlib.util.find_spec("mcp") is not None
PLUGIN_ROOT = Path(__file__).resolve().parents[2]


@unittest.skipUnless(HAS_MCP, "MCP runtime dependencies are not installed")
class CodexStartupTests(unittest.TestCase):
    def test_relocated_package_exposes_existing_tools(self) -> None:
        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client

        manifest = json.loads(
            (PLUGIN_ROOT / ".codex-plugin" / "plugin.json").read_text()
        )
        # An inline server map is authoritative in Codex's legacy plugin loader;
        # it avoids also discovering the Claude-specific default .mcp.json.
        servers = manifest["mcpServers"]
        self.assertEqual(set(servers), {"praxys"})
        config = servers["praxys"]

        with tempfile.TemporaryDirectory(prefix="praxys plugin ") as temporary:
            root = Path(temporary)
            shutil.copytree(PLUGIN_ROOT / "mcp-server", root / "mcp-server")
            # Codex resolves relative cwd against the installed plugin root.
            # Resolve python using this test's activated environment, as in setup.
            env = {
                **os.environ,
                "PATH": str(Path(sys.executable).parent) + os.pathsep + os.defpath,
                "PRAXYS_LOCAL": "0",
                "TRAINSIGHT_LOCAL": "0",
                "PRAXYS_TOKEN_PATH": str(root / "unused-token"),
            }
            env.pop("CLAUDE_PLUGIN_ROOT", None)
            env.pop("PLUGIN_ROOT", None)
            parameters = StdioServerParameters(
                command=config["command"],
                args=config["args"],
                cwd=str(root / config["cwd"]),
                env=env,
            )

            async def probe() -> None:
                async with stdio_client(parameters) as (read, write):
                    async with ClientSession(read, write) as session:
                        await session.initialize()
                        result = await session.list_tools()
                        names = {tool.name for tool in result.tools}
                        self.assertTrue(
                            {"login", "whoami", "get_daily_brief", "save_training_plan"}
                            <= names
                        )

            async def run_with_timeout() -> None:
                await asyncio.wait_for(probe(), timeout=20)

            asyncio.run(run_with_timeout())


if __name__ == "__main__":
    unittest.main()
