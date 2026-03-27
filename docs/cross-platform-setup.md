# Cross-Platform Setup Guide

All plugins in this marketplace work on macOS, Linux, and Windows (via WSL2). Docker abstracts away most OS differences — once Docker is running, the MCP servers behave the same everywhere.

## Support Matrix

| | macOS | Linux | Windows (WSL2) |
|---|---|---|---|
| **Docker** | Docker Desktop | Docker Engine or Desktop | Docker Desktop (WSL2 backend) |
| **Scripts** | `.sh` runs natively | `.sh` runs natively | `.sh` runs natively inside WSL2 |
| **Line endings** | LF (enforced by `.gitattributes`) | LF | LF (enforced by `.gitattributes`) |

## macOS / Linux

1. Install Docker ([Desktop](https://www.docker.com/products/docker-desktop/) for macOS, [Engine](https://docs.docker.com/engine/install/) or Desktop for Linux)
2. Clone the repo and install plugins per the [README](../README.md#installation)

macOS note: the launch scripts use `xargs -r` (a GNU extension) for old container cleanup. On macOS this is silenced automatically — no action needed.

## Windows (WSL2)

WSL2 provides a full Linux kernel inside Windows. All tools and scripts work natively within the WSL2 environment.

### Setup

1. Install [WSL2](https://learn.microsoft.com/en-us/windows/wsl/install) (Ubuntu recommended)
2. Install [Docker Desktop](https://www.docker.com/products/docker-desktop/) and enable the WSL2 backend (Settings → Resources → WSL Integration)
3. **Clone the repo inside the WSL2 filesystem** (e.g., `~/pddl-copilot`), not on the Windows mount (`/mnt/c/`). File operations across the OS boundary are slow and can cause issues with file watchers.
4. Install plugins from within a WSL2 terminal per the [README](../README.md#installation)

### Tips

- Run `claude` from a WSL2 terminal (Windows Terminal with Ubuntu tab, or any WSL2 shell)
- Cursor can connect to WSL2 via the "Remote - WSL" extension — MCP configs use WSL2 paths
- Docker containers run in the WSL2 Linux kernel, so no additional Docker configuration is needed beyond enabling the WSL2 backend

## MCP Configuration Paths

When using `install_marketplace.sh`, configs are written automatically. For manual setup:

| Tool | Config file location |
|------|---------------------|
| **Claude Code** | Managed by `claude` CLI (no manual config needed) |
| **Cursor** | `~/.cursor/mcp.json` |
| **Antigravity** | `~/.gemini/antigravity/mcp_config.json` |

All `.mcp.json` files use `${CLAUDE_PLUGIN_ROOT}` for portable path substitution — the installer resolves this to an absolute path on your system.

## Troubleshooting

### GHCR image pull fails

If the pull fails (e.g., firewall, proxy), the launch script automatically falls back to building locally from source (~15 min on first build).

### WSL2: slow file operations

If you cloned the repo to `/mnt/c/...` (the Windows filesystem), move it to the WSL2 native filesystem (`~/`). Cross-filesystem operations are significantly slower and can cause Docker volume mount issues.

### WSL2: Docker not available

Ensure Docker Desktop's WSL2 integration is enabled for your distro: Docker Desktop → Settings → Resources → WSL Integration → enable your Ubuntu/Debian distro.
