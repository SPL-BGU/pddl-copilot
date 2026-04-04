# PDDL Copilot — Plugin Marketplace

A Claude Code plugin marketplace for PDDL planning and validation tools.

## Available Plugins

| Plugin | Description |
|--------|-------------|
| [pddl-solver](plugins/pddl-solver/) | Compute plans using Fast Downward (classical) and Metric-FF (numeric) in Docker |
| [pddl-validator](plugins/pddl-validator/) | Validate PDDL syntax, plans, and simulate state transitions using VAL in Docker |
| [pddl-parser](plugins/pddl-parser/) | Parse PDDL domains/problems and generate structured trajectories (pure Python, no Docker) |

## Prerequisites

- [Docker](https://docker.com) must be installed and running (required for `pddl-solver` and `pddl-validator`; `pddl-parser` is pure Python and does not require Docker)

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
   │  ▸ pddl-solver                                   │
   │    PDDL planning with Fast Downward & Metric-FF  │
   │    pddl-validator                                │
   │    PDDL validation with VAL                      │
   │    pddl-parser                                   │
   │    PDDL parsing and structured trajectories      │
   └─────────────────────────────────────────────────┘
   ```

6. Press **Escape** to exit the plugins view and return to your session.

Plugins are installed globally — start Claude Code from any project directory to use them.

### Alternative: Load a specific plugin directly (development)

```bash
claude --plugin-dir ./plugins/pddl-solver
claude --plugin-dir ./plugins/pddl-validator
claude --plugin-dir ./plugins/pddl-parser
```

## Use with Other AI Tools

The MCP servers and skills are portable — any tool that supports the [Model Context Protocol](https://modelcontextprotocol.io) can use them. Currently supported: **Cursor** and **Google Antigravity**.

### Marketplace-Wide Setup (all plugins at once)

```bash
bash install_marketplace.sh --install
```

This auto-discovers all plugins, writes MCP configs, and symlinks skills to detected tools. Use `--tool cursor` or `--tool antigravity` for a specific tool.

### Manual Setup (Cursor / Antigravity)

Both tools need two things: an MCP server config and skill symlinks.

**MCP config** — add to `~/.cursor/mcp.json` (Cursor) or `~/.gemini/antigravity/mcp_config.json` (Antigravity):
```json
{
  "mcpServers": {
    "pddl-solver": {
      "command": "bash",
      "args": ["/absolute/path/to/plugins/pddl-solver/scripts/launch-server.sh"]
    },
    "pddl-validator": {
      "command": "bash",
      "args": ["/absolute/path/to/plugins/pddl-validator/scripts/launch-server.sh"]
    },
    "pddl-parser": {
      "command": "bash",
      "args": ["/absolute/path/to/plugins/pddl-parser/scripts/launch-server.sh"]
    }
  }
}
```

**Skills** — symlink the plugins' skills to the tool's global skills directory:
```bash
# Cursor
ln -sfn /absolute/path/to/plugins/pddl-solver/skills/pddl-planning ~/.cursor/skills/pddl-planning
ln -sfn /absolute/path/to/plugins/pddl-validator/skills/pddl-validation ~/.cursor/skills/pddl-validation
ln -sfn /absolute/path/to/plugins/pddl-parser/skills/pddl-parsing ~/.cursor/skills/pddl-parsing

# Antigravity
ln -sfn /absolute/path/to/plugins/pddl-solver/skills/pddl-planning ~/.gemini/antigravity/skills/pddl-planning
ln -sfn /absolute/path/to/plugins/pddl-validator/skills/pddl-validation ~/.gemini/antigravity/skills/pddl-validation
ln -sfn /absolute/path/to/plugins/pddl-parser/skills/pddl-parsing ~/.gemini/antigravity/skills/pddl-parsing
```

Replace `/absolute/path/to` with the actual path where you cloned this repo.

For OS-specific setup (macOS, Linux, Windows/WSL2), see [docs/cross-platform-setup.md](docs/cross-platform-setup.md).

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
python3 ollama_mcp_bridge.py --model qwen3:4b --plugins pddl-solver,pddl-validator,pddl-parser
```

### Requirements

- [Ollama](https://ollama.com) installed and running (`ollama serve`)
- A model with tool-calling support (e.g., `llama3.1`, `qwen3`, `mistral`)
- Docker (for plugins that require it)

## Adding a New Plugin

See [docs/contributing.md](docs/contributing.md#creating-a-new-plugin) for the full guide.

## Repository Structure

```
pddl-copilot/
├── .claude-plugin/
│   ├── plugin.json            # Marketplace metadata
│   └── marketplace.json       # Plugin catalog (lists all plugins)
├── .cursor-plugin/
│   ├── plugin.json            # Cursor marketplace metadata
│   └── marketplace.json       # Cursor plugin catalog
├── docs/
│   ├── architecture.md        # Architecture tiers, patterns, conventions
│   ├── contributing.md        # How to contribute and create plugins
│   ├── cross-platform-setup.md # macOS, Linux, Windows (WSL2) setup
│   └── branch-testing.md     # Testing branches on other machines
├── docker/
│   ├── Dockerfile             # Shared Docker image (FD, MFF, VAL)
│   └── solvers_server_wrapper.py
├── plugins/
│   ├── pddl-solver/           # Planning plugin
│   │   ├── .mcp.json
│   │   ├── CLAUDE.md
│   │   ├── .claude/settings.json
│   │   ├── server/solver_server.py
│   │   ├── skills/pddl-planning/
│   │   ├── scripts/launch-server.sh
│   │   └── tests/verify.sh
│   ├── pddl-validator/        # Validation plugin
│   │   ├── .mcp.json
│   │   ├── CLAUDE.md
│   │   ├── .claude/settings.json
│   │   ├── server/validator_server.py
│   │   ├── skills/pddl-validation/
│   │   ├── scripts/launch-server.sh
│   │   └── tests/verify.sh
│   └── pddl-parser/           # Parsing plugin (pure Python)
│       ├── .mcp.json
│       ├── CLAUDE.md
│       ├── .claude/settings.json
│       ├── server/parser_server.py
│       ├── skills/pddl-parsing/
│       ├── scripts/launch-server.sh
│       └── tests/verify.sh
├── tests/
│   ├── static_checks.sh       # Config & structure validation (no Docker)
│   └── mcp_protocol_test.sh   # MCP stdio protocol smoke tests
├── .github/workflows/
│   ├── docker-publish.yml     # Multi-arch Docker image build & push
│   └── integration.yml        # PR gate: static checks + plugin tests + MCP protocol
├── install_marketplace.sh     # Unified Cursor/Antigravity installer
├── CLAUDE.md                  # Marketplace-level instructions
├── ollama_mcp_bridge.py       # Ollama MCP Bridge CLI
├── requirements-bridge.txt    # Bridge dependencies
├── LICENSE
└── README.md
```

## License

MIT
