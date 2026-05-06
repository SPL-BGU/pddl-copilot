#!/usr/bin/env python3
"""Verify each plugin's MCP server registers all expected tools via the MCP
stdio protocol. Catches @mcp.tool() decorator / FastMCP wiring bugs that
direct Python imports would miss.

Skills-only plugins (no .mcp.json) are skipped: there is no server to probe.
"""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

GREEN = "\033[0;32m"
RED = "\033[0;31m"
NC = "\033[0m"

# Plugins probed by this script. Note: pddl-parser is intentionally not listed
# here — its MCP coverage is exercised by its own verify.py. Add it if/when
# parity is desired.
PLUGINS = [
    ("pddl-solver", {"classic_planner", "numeric_planner", "save_plan"}, "solver_server.py"),
    ("pddl-validator", {"validate_pddl_syntax", "get_state_transition"}, "validator_server.py"),
]


class Reporter:
    def __init__(self) -> None:
        self.failures = 0

    def ok(self, msg: str) -> None:
        print(f"  {GREEN}OK{NC}  {msg}")

    def fail(self, msg: str) -> None:
        print(f"  {RED}FAIL{NC} {msg}")
        self.failures += 1


def ensure_venv(plugin_dir: Path) -> Path:
    venv_dir = plugin_dir / ".venv"
    if not venv_dir.is_dir():
        print(f"  Setting up {plugin_dir.name} venv...")
        if shutil.which("uv"):
            subprocess.check_call(["uv", "venv", str(venv_dir)])
            subprocess.check_call([
                "uv", "pip", "install",
                "--python", str(venv_dir / "bin" / "python3"),
                "-r", str(plugin_dir / "requirements.txt"),
            ])
        else:
            subprocess.check_call([sys.executable, "-m", "venv", str(venv_dir)])
            subprocess.check_call([
                str(venv_dir / "bin" / "pip"), "install",
                "--quiet", "-r", str(plugin_dir / "requirements.txt"),
            ])
    return venv_dir / "bin" / "python3"


def probe_plugin(reporter: Reporter, plugin_name: str, expected: set[str], server_filename: str) -> None:
    print(f"--- {plugin_name} (Tier 1) ---")
    plugin_dir = REPO_ROOT / "plugins" / plugin_name
    if not (plugin_dir / ".mcp.json").is_file():
        print(f"  skipped — no .mcp.json (skills-only plugin)")
        return

    venv_python = ensure_venv(plugin_dir)
    server_path = plugin_dir / "server" / server_filename

    # The probe uses the venv python, which has the `mcp` package installed.
    # We invoke a subprocess so we're not bound to the harness's python.
    probe_script = (
        "import asyncio, sys\n"
        "from mcp import ClientSession, StdioServerParameters\n"
        "from mcp.client.stdio import stdio_client\n"
        "async def main():\n"
        "    expected = set(sys.argv[1].split(','))\n"
        "    params = StdioServerParameters(command=sys.argv[2], args=[sys.argv[3]])\n"
        "    async with stdio_client(params) as (read, write):\n"
        "        async with ClientSession(read, write) as session:\n"
        "            await session.initialize()\n"
        "            result = await session.list_tools()\n"
        "            registered = {t.name for t in result.tools}\n"
        "            print(f'Registered: {sorted(registered)}')\n"
        "            missing = expected - registered\n"
        "            if missing:\n"
        "                print(f'MISSING: {sorted(missing)}', file=sys.stderr)\n"
        "                sys.exit(1)\n"
        "            print('ALL_TOOLS_OK')\n"
        "asyncio.run(main())\n"
    )

    rc = subprocess.run(
        [str(venv_python), "-c", probe_script, ",".join(sorted(expected)),
         str(venv_python), str(server_path)],
        capture_output=True, text=True,
    )
    if "ALL_TOOLS_OK" in rc.stdout:
        reporter.ok(f"all {len(expected)} tools registered")
    else:
        reporter.fail(f"{plugin_name} tools/list")
        if rc.stdout:
            print(rc.stdout, file=sys.stderr)
        if rc.stderr:
            print(rc.stderr, file=sys.stderr)


def main() -> int:
    reporter = Reporter()
    print("=== MCP Protocol Smoke Tests ===")
    print()

    for i, (name, expected, server_filename) in enumerate(PLUGINS):
        if i > 0:
            print()
        probe_plugin(reporter, name, expected, server_filename)

    print()
    if reporter.failures > 0:
        print(f"{RED}{reporter.failures} MCP protocol test(s) failed.{NC}")
        return 1
    print(f"{GREEN}All MCP protocol tests passed.{NC}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
