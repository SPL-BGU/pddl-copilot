# Cross-Platform Setup Guide

All plugins in this marketplace work on macOS, Linux, and Windows (via WSL2). All plugins are pure pip (Tier 1) — no Docker or compiled binaries required.

## Support Matrix

| | macOS | Linux | Windows (WSL2) |
|---|---|---|---|
| **Python** | 3.10+ | 3.10+ | 3.10+ (inside WSL2) |
| **Scripts** | `.sh` runs natively | `.sh` runs natively | `.sh` runs natively inside WSL2 |
| **Line endings** | LF (enforced by `.gitattributes`) | LF | LF (enforced by `.gitattributes`) |

## macOS / Linux

1. Ensure Python 3.10+ is installed
2. Clone the repo and install plugins per the [README](../README.md#installation)

## Windows (WSL2)

WSL2 provides a full Linux kernel inside Windows. All tools and scripts work natively within the WSL2 environment.

### Setup

1. Install [WSL2](https://learn.microsoft.com/en-us/windows/wsl/install) (Ubuntu recommended)
2. Ensure Python 3.10+ is installed inside WSL2
3. **Clone the repo inside the WSL2 filesystem** (e.g., `~/pddl-copilot`), not on the Windows mount (`/mnt/c/`). File operations across the OS boundary are slow and can cause issues with file watchers.
4. Install plugins from within a WSL2 terminal per the [README](../README.md#installation)

### Tips

- Run `claude` from a WSL2 terminal (Windows Terminal with Ubuntu tab, or any WSL2 shell)
- Cursor can connect to WSL2 via the "Remote - WSL" extension — MCP configs use WSL2 paths

## MCP Configuration Paths

When using `install_marketplace.sh`, configs are written automatically. For manual setup:

| Tool | Config file location |
|------|---------------------|
| **Claude Code** | Managed by `claude` CLI (no manual config needed) |
| **Cursor** | `~/.cursor/mcp.json` |
| **Antigravity** | `~/.gemini/antigravity/mcp_config.json` |

All `.mcp.json` files use `${CLAUDE_PLUGIN_ROOT}` for portable path substitution — the installer resolves this to an absolute path on your system.

## Troubleshooting

### WSL2: slow file operations

If you cloned the repo to `/mnt/c/...` (the Windows filesystem), move it to the WSL2 native filesystem (`~/`). Cross-filesystem operations are significantly slower.
