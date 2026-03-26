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

The MCP server and skills are portable — any tool that supports the [Model Context Protocol](https://modelcontextprotocol.io) can use them. Currently supported: **Cursor** and **Google Antigravity**.

### Automatic Setup

```bash
bash plugins/pddl-planning-copilot/scripts/setup.sh --install
```

This writes MCP configs and symlinks skills to detected tools. Use `--tool cursor` or `--tool antigravity` for a specific tool.

### Manual Setup

Both tools need two things: an MCP server config and skill symlinks.

**MCP config** — add to `~/.cursor/mcp.json` (Cursor) or `~/.gemini/antigravity/mcp_config.json` (Antigravity):
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

**Skills** — symlink the plugin's skills to the tool's global skills directory:
```bash
# Cursor
ln -sfn /absolute/path/to/plugins/pddl-planning-copilot/skills/pddl-planning ~/.cursor/skills/pddl-planning
ln -sfn /absolute/path/to/plugins/pddl-planning-copilot/skills/pddl-validation ~/.cursor/skills/pddl-validation

# Antigravity
ln -sfn /absolute/path/to/plugins/pddl-planning-copilot/skills/pddl-planning ~/.gemini/antigravity/skills/pddl-planning
ln -sfn /absolute/path/to/plugins/pddl-planning-copilot/skills/pddl-validation ~/.gemini/antigravity/skills/pddl-validation
```

Replace `/absolute/path/to` with the actual path where you cloned this repo.

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
