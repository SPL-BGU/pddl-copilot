# PDDL Copilot — Plugin Marketplace

A Claude Code plugin marketplace for PDDL planning tools.

## Available Plugins

| Plugin | Description |
|--------|-------------|
| [pddl-planning-copilot](plugins/pddl-planning-copilot/) | PDDL planning, validation & simulation via Fast Downward, Metric-FF, and VAL in Docker |

## Prerequisites

- [Docker](https://docker.com) must be installed and running
- [Claude Code](https://claude.com/claude-code) CLI

## Installation

### Install from the marketplace (recommended)

1. Start a Claude Code session:
   ```bash
   claude
   ```

2. Inside the session, type `/plugins` to open the plugins view:
   ```
   /plugins
   ```
   This opens the **Plugins Manager** screen with three tabs:

   ```
   ┌─────────────────────────────────────────────────┐
   │  Installed    Available    Marketplace Search  → │
   └─────────────────────────────────────────────────┘
   ```

3. Press the **right arrow key** (→) twice to navigate to the **Marketplace Search** tab:

   ```
   ┌─────────────────────────────────────────────────┐
   │  Installed    Available  ▸ Marketplace Search    │
   ├─────────────────────────────────────────────────┤
   │  Search: _                                       │
   │                                                  │
   │  Enter a GitHub owner/repo to search             │
   └─────────────────────────────────────────────────┘
   ```

4. Type the marketplace path and press **Enter**:
   ```
   SPL-BGU/pddl-copilot
   ```

5. Select a plugin from the results list and confirm installation:

   ```
   ┌─────────────────────────────────────────────────┐
   │  Marketplace Search                              │
   ├─────────────────────────────────────────────────┤
   │  ▸ pddl-planning-copilot                        │
   │    PDDL planning, validation & simulation tools  │
   └─────────────────────────────────────────────────┘
   ```

6. Press **Escape** to exit the plugins view and return to your session.

The plugin is now installed globally — start Claude Code from any project directory to use it.

### Alternative: Load a specific plugin directly (development)

```bash
claude --plugin-dir ./plugins/pddl-planning-copilot
```

## Use with Other AI Tools

The MCP server is portable — any tool that supports the [Model Context Protocol](https://modelcontextprotocol.io) can use it. Currently supported: **Cursor**, **OpenAI Codex CLI**, and **Google Antigravity**.

### Quick Setup

```bash
bash plugins/pddl-planning-copilot/scripts/setup.sh
```

This prints the correct MCP config for each detected tool. Use `--tool <name>` for a specific tool, or `--install` to write configs automatically.

### Manual Setup

All platforms need the same thing: point an MCP stdio server at the launch script.

**Cursor** — add to `.cursor/mcp.json` (project) or `~/.cursor/mcp.json` (global):
```json
{
  "mcpServers": {
    "pddl-planner": {
      "command": "bash",
      "args": ["/absolute/path/to/plugins/pddl-planning-copilot/scripts/launch-server.sh"]
    }
  }
}
```

**OpenAI Codex CLI** — run:
```bash
codex mcp add pddl-planner -- bash /absolute/path/to/plugins/pddl-planning-copilot/scripts/launch-server.sh
```

**Google Antigravity** — add to `~/.gemini/antigravity/mcp_config.json`:
```json
{
  "mcpServers": {
    "pddl-planner": {
      "command": "bash",
      "args": ["/absolute/path/to/plugins/pddl-planning-copilot/scripts/launch-server.sh"]
    }
  }
}
```

Replace `/absolute/path/to` with the actual path where you cloned this repo.

### Agent Instructions

For best results, add the contents of [`plugins/pddl-planning-copilot/INSTRUCTIONS.md`](plugins/pddl-planning-copilot/INSTRUCTIONS.md) to your tool's custom rules or system prompt. This teaches the AI the mandatory workflow (never self-generate plans, always validate, etc.).

| Tool | Where to add instructions |
|------|--------------------------|
| Cursor | `.cursor/rules/pddl-planning.md` |
| Codex CLI | Custom instructions in config |
| Antigravity | System prompt / custom rules |

## Ollama MCP Bridge (Experimental)

A CLI tool that connects local Ollama models to MCP plugins from this marketplace. Lets open-source LLMs use the same planning tools as Claude Code.

### Setup

```bash
pip3 install -r requirements-bridge.txt
```

### Usage

```bash
python3 ollama_mcp_bridge.py
```

Or non-interactively:

```bash
python3 ollama_mcp_bridge.py --model qwen3:4b --plugins pddl-planning-copilot
```

### Requirements

- [Ollama](https://ollama.com) installed and running (`ollama serve`)
- A model with tool-calling support (e.g., `llama3.1`, `qwen3`, `mistral`)
- Docker (for plugins that require it, like pddl-planning-copilot)

## Adding a New Plugin

1. Create a directory under `plugins/<your-plugin-name>/`
2. Add the required plugin files:
   - `.mcp.json` — MCP server configuration
   - `CLAUDE.md` — enforcement rules for Claude
   - `.claude/settings.json` — pre-approved tool permissions
   - `skills/` — auto-discovered skills (optional)
   - `scripts/` — launch scripts, etc.
3. Add an entry to `.claude-plugin/marketplace.json`:
   ```json
   {
     "name": "your-plugin-name",
     "description": "What your plugin does",
     "author": { "name": "Your Name" },
     "license": "MIT",
     "version": "1.0.0",
     "source": "plugins/your-plugin-name",
     "homepage": "https://github.com/...",
     "repository": "https://github.com/...",
     "category": "your-category",
     "keywords": ["keyword1", "keyword2"]
   }
   ```

## Repository Structure

```
pddl-copilot/
├── .claude-plugin/
│   ├── plugin.json            # Marketplace metadata
│   └── marketplace.json       # Plugin catalog (lists all plugins)
├── plugins/
│   └── pddl-planning-copilot/ # PDDL planning plugin
│       ├── .mcp.json
│       ├── CLAUDE.md
│       ├── .claude/settings.json
│       ├── skills/
│       ├── scripts/
│       ├── docker/
│       └── docs/
├── .github/workflows/         # CI/CD (shared)
├── CLAUDE.md                  # Marketplace-level instructions
├── ollama_mcp_bridge.py       # Ollama MCP Bridge CLI
├── requirements-bridge.txt    # Bridge dependencies
├── LICENSE
└── README.md
```

## License

MIT
