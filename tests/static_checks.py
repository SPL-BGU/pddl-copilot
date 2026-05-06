#!/usr/bin/env python3
"""Fast static validation of plugin structure and configuration.

Catches broken JSON, missing files, stale settings, etc. No Docker required.
"""
from __future__ import annotations

import ast
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

GREEN = "\033[0;32m"
RED = "\033[0;31m"
NC = "\033[0m"


class Reporter:
    def __init__(self) -> None:
        self.failures = 0

    def ok(self, msg: str) -> None:
        print(f"  {GREEN}OK{NC}  {msg}")

    def fail(self, msg: str) -> None:
        print(f"  {RED}FAIL{NC} {msg}")
        self.failures += 1


def parse_json(path: Path) -> tuple[bool, dict | None, str]:
    try:
        with path.open() as f:
            return True, json.load(f), ""
    except Exception as e:
        return False, None, str(e)


def rel(path: Path) -> str:
    try:
        return str(path.relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


def check_marketplace_json_validity(reporter: Reporter, marketplaces: list[Path]) -> None:
    print("--- JSON validity ---")
    for f in marketplaces:
        ok, _, err = parse_json(f)
        if ok:
            reporter.ok(rel(f))
        else:
            reporter.fail(f"{rel(f)} — invalid JSON: {err}")


def check_marketplace_directories(reporter: Reporter, marketplaces: list[Path]) -> None:
    print()
    print("--- Marketplace ↔ plugin directories ---")
    for marketplace in marketplaces:
        ok, data, _ = parse_json(marketplace)
        if not ok:
            continue
        for p in data.get("plugins", []):
            src = p["source"]
            plugin_dir = REPO_ROOT / src.lstrip("./")
            label = rel(marketplace)
            if plugin_dir.is_dir():
                reporter.ok(f"{label} → {src} exists")
            else:
                reporter.fail(f"{label} → {src} directory missing")


def check_plugin_required_files(reporter: Reporter, plugin_dir: Path) -> None:
    plugin_name = plugin_dir.name

    if (plugin_dir / "CLAUDE.md").is_file():
        reporter.ok(f"{plugin_name}/CLAUDE.md")
    else:
        reporter.fail(f"{plugin_name}/CLAUDE.md missing")

    mcp_json = plugin_dir / ".mcp.json"
    has_skills = (plugin_dir / "skills").is_dir()
    if not mcp_json.is_file() and not has_skills:
        reporter.fail(f"{plugin_name} has neither .mcp.json nor skills/ — not a valid plugin")

    if mcp_json.is_file():
        ok, _, err = parse_json(mcp_json)
        if ok:
            reporter.ok(f"{plugin_name}/.mcp.json valid JSON")
        else:
            reporter.fail(f"{plugin_name}/.mcp.json invalid JSON: {err}")

        # MCP plugins must ship pre-approved permissions
        # (see .claude/rules/marketplace.md#adding-a-new-plugin-checklist)
        settings = plugin_dir / ".claude" / "settings.json"
        if settings.is_file():
            reporter.ok(f"{plugin_name}/.claude/settings.json present")
        else:
            reporter.fail(f"{plugin_name} has .mcp.json but missing .claude/settings.json")

    settings = plugin_dir / ".claude" / "settings.json"
    if settings.is_file():
        ok, _, err = parse_json(settings)
        if ok:
            reporter.ok(f"{plugin_name}/.claude/settings.json valid JSON")
        else:
            reporter.fail(f"{plugin_name}/.claude/settings.json invalid JSON: {err}")


def check_launch_scripts_exist(reporter: Reporter, plugin_dir: Path) -> None:
    plugin_name = plugin_dir.name
    mcp_json = plugin_dir / ".mcp.json"
    if not mcp_json.is_file():
        return
    ok, data, _ = parse_json(mcp_json)
    if not ok:
        return
    for srv in data.get("mcpServers", {}).values():
        for arg in srv.get("args", []):
            resolved = arg.replace("${CLAUDE_PLUGIN_ROOT}", str(plugin_dir))
            if not (resolved.endswith(".sh") or resolved.endswith(".py")):
                continue
            script = Path(resolved)
            if script.is_file():
                reporter.ok(f"{plugin_name} launch script: {script.name}")
            else:
                reporter.fail(f"{plugin_name} launch script missing: {resolved}")


def check_python_syntax(reporter: Reporter, plugins_dir: Path) -> None:
    print()
    print("--- Python syntax ---")
    for server_py in sorted(plugins_dir.glob("*/server/*.py")):
        try:
            ast.parse(server_py.read_text())
            reporter.ok(rel(server_py))
        except SyntaxError as e:
            reporter.fail(f"{rel(server_py)} — syntax error: {e}")


def server_tool_names(server_dir: Path) -> set[str]:
    """Extract tool names from @mcp.tool decorated functions in server files.

    Handles both @mcp.tool() (uses function name) and @mcp.tool(name='custom').
    """
    tools: set[str] = set()
    if not server_dir.is_dir():
        return tools
    for f in sorted(server_dir.iterdir()):
        if not f.suffix == ".py":
            continue
        tree = ast.parse(f.read_text())
        for node in ast.walk(tree):
            if not isinstance(node, ast.FunctionDef):
                continue
            for dec in node.decorator_list:
                src = ast.dump(dec)
                if "mcp" not in src or "tool" not in src:
                    continue
                tool_name = node.name
                if isinstance(dec, ast.Call):
                    for kw in dec.keywords:
                        if kw.arg == "name" and isinstance(kw.value, ast.Constant):
                            tool_name = kw.value.value
                tools.add(tool_name)
    return tools


def settings_tool_names(settings_path: Path, server_name: str) -> set[str]:
    ok, data, _ = parse_json(settings_path)
    if not ok:
        return set()
    prefix = f"mcp__{server_name}__"
    return {
        tool[len(prefix):]
        for tool in data.get("permissions", {}).get("allow", [])
        if tool.startswith(prefix)
    }


def first_mcp_server_name(mcp_json_path: Path) -> str | None:
    ok, data, _ = parse_json(mcp_json_path)
    if not ok:
        return None
    for name in data.get("mcpServers", {}):
        return name
    return None


def check_settings_server_consistency(reporter: Reporter, plugin_dir: Path) -> None:
    plugin_name = plugin_dir.name
    settings = plugin_dir / ".claude" / "settings.json"
    mcp_json = plugin_dir / ".mcp.json"
    if not settings.is_file() or not mcp_json.is_file():
        return

    server_name = first_mcp_server_name(mcp_json)
    if not server_name:
        return

    settings_tools = settings_tool_names(settings, server_name)
    server_tools = server_tool_names(plugin_dir / "server")

    for tool in sorted(settings_tools):
        if tool in server_tools:
            reporter.ok(f"{plugin_name} settings: {tool} found in server")
        else:
            reporter.fail(f"{plugin_name} settings: {tool} NOT found in server")

    for tool in sorted(server_tools):
        if tool in settings_tools:
            reporter.ok(f"{plugin_name} server: {tool} has settings entry")
        else:
            reporter.fail(f"{plugin_name} server: {tool} MISSING from settings.json")


def main() -> int:
    reporter = Reporter()
    print("=== Static Checks ===")
    print()

    marketplaces = [
        REPO_ROOT / ".claude-plugin" / "marketplace.json",
        REPO_ROOT / ".cursor-plugin" / "marketplace.json",
    ]

    check_marketplace_json_validity(reporter, marketplaces)
    check_marketplace_directories(reporter, marketplaces)

    plugins_dir = REPO_ROOT / "plugins"
    plugin_dirs = sorted(p for p in plugins_dir.iterdir() if p.is_dir())

    print()
    print("--- Plugin required files ---")
    for plugin_dir in plugin_dirs:
        check_plugin_required_files(reporter, plugin_dir)

    print()
    print("--- Launch script existence ---")
    for plugin_dir in plugin_dirs:
        check_launch_scripts_exist(reporter, plugin_dir)

    check_python_syntax(reporter, plugins_dir)

    print()
    print("--- Settings ↔ server tool consistency ---")
    for plugin_dir in plugin_dirs:
        check_settings_server_consistency(reporter, plugin_dir)

    print()
    if reporter.failures > 0:
        print(f"{RED}{reporter.failures} check(s) failed.{NC}")
        return 1
    print(f"{GREEN}All static checks passed.{NC}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
