"""MCP runtime dependency contract tests."""

import importlib.util
from pathlib import Path
import unittest


if importlib.util.find_spec("mcp") is None:
    FastMCP = None
else:
    from mcp.server.fastmcp import FastMCP


REQUIREMENTS_PATH = Path(__file__).resolve().parents[1] / "requirements.txt"


class RequirementsTests(unittest.TestCase):
    def test_mcp_sdk_pins_verified_fastmcp_release(self) -> None:
        requirements = REQUIREMENTS_PATH.read_text(encoding="utf-8").splitlines()

        self.assertIn("mcp==1.28.1", requirements)

    @unittest.skipIf(FastMCP is None, "MCP runtime dependencies are not installed")
    def test_pinned_sdk_exposes_fastmcp(self) -> None:
        self.assertTrue(callable(FastMCP))


if __name__ == "__main__":
    unittest.main()
