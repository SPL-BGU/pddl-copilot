# PDDL Copilot — Claude Code Plugin

A Claude Code plugin that provides PDDL planning, validation, and simulation tools
using Fast Downward, Metric-FF, and VAL pre-compiled in a Docker image.
Based on [arXiv:2509.12987](https://arxiv.org/abs/2509.12987).

## Prerequisites

- [Docker](https://docker.com) must be installed and running
- [Claude Code](https://claude.com/claude-code) CLI

## Installation

### Install as a plugin (recommended)

```bash
claude install-plugin https://github.com/SPL-BGU/pddl-copilot.git
```

Then start Claude Code from any project directory — the plugin is available globally.

### Alternative: Clone and run directly

```bash
git clone https://github.com/SPL-BGU/pddl-copilot.git
cd pddl-copilot
claude
```

### Alternative: Load as a local plugin (development)

```bash
claude --plugin-dir ./pddl-copilot
```

### Alternative: Add to an existing project

Add the MCP server to your project's `.mcp.json`:

```json
{
  "mcpServers": {
    "pddl-planner": {
      "command": "bash",
      "args": ["/absolute/path/to/pddl-copilot/scripts/launch-server.sh"]
    }
  }
}
```

### First run

On your **first planning request**, the plugin automatically:
1. Pulls the pre-built Docker image from GHCR (~30-60 seconds)
2. Starts the MCP server inside the container
3. Runs your planning task

Every session after that starts in ~2 seconds.

If the GHCR pull fails (e.g., no internet), the plugin falls back to building
the image locally from source (~15 min, compiles all three planners).

## Usage Examples

Once installed, just describe what you want in natural language:

```
Solve the blocksworld problem in problems/bw1.pddl using domains/blocksworld.pddl
```

```
Write a PDDL domain for a logistics problem and solve it
```

```
Validate my domain file domain.pddl and problem file problem.pddl
```

```
Solve problems/depots-p01.pddl and show the state transitions step by step
```

The plugin enforces correct behavior — Claude will always use the planner tools (never guess plans) and always validate results.

## Why Docker?

Fast Downward, Metric-FF, and VAL are heavy C++ binaries (10–20 min compile time).
They cannot be compiled at plugin-enable time — it would timeout and not persist
between sessions. Instead, a pre-built Docker image is pulled from GHCR on first
use (~30-60s) and the binaries are just there, ready instantly.

## Available Tools

| Tool | What it does |
|------|-------------|
| `classic_planner(domain, problem, strategy?)` | Solves classical PDDL via Fast Downward |
| `numeric_planner(domain, problem)` | Solves PDDL 2.1 with numeric fluents via Metric-FF |
| `validate_pddl_syntax(domain, problem, plan)` | Validates PDDL and plans via VAL |
| `save_plan(plan, domain?, name?)` | Saves a plan to a file |
| `get_state_transition(domain, problem, plan)` | Simulates execution, returns state trace |

**Tools accept inline PDDL content strings OR file paths.** The MCP server
auto-detects which was provided — if the input starts with `(`, it writes a temp file
internally. This avoids host/container path-mapping issues.

### Fast Downward search strategies

The `classic_planner` tool supports an optional `strategy` parameter:

| Strategy | Description |
|----------|-------------|
| `lazy_greedy_cea` (default) | Lazy greedy search with context-enhanced additive heuristic |
| `astar_lmcut` | A* search with landmark-cut heuristic (optimal) |
| `lazy_greedy_ff` | Lazy greedy search with FF heuristic |

## What's Inside the Docker Image

| Component | Source | Location in image |
|-----------|--------|--------------------|
| Fast Downward | [aibasel/downward](https://github.com/aibasel/downward) | `/opt/planners/FastDownward/` |
| Metric-FF | [HenryKautz/Metric-FF](https://github.com/HenryKautz/Metric-FF) | `/opt/planners/METRIC_FF/` |
| VAL | [KCL-Planning/VAL](https://github.com/KCL-Planning/VAL) | `/opt/planners/VAL/` |

## How It Works

```
Claude Code starts
  → loads .mcp.json → runs scripts/launch-server.sh
    → checks: Docker installed?
    → checks: pddl-sandbox image exists locally?
      → NO: docker pull from GHCR (~30-60s)
        → pull failed? fallback: docker build (~15 min, once ever)
      → YES: instant
    → docker run -i pddl-sandbox python3 -m pddl_server
      → MCP server running, tools registered
  → CLAUDE.md + skills inject enforcement rules
  → Claude calls classic_planner / numeric_planner / validate_pddl_syntax
  → tool runs inside the container
  → result returned to Claude
  → session ends → container auto-removed, image stays
```

## How Enforcement Works

1. **CLAUDE.md** loads mandatory rules: never generate plans, always validate, always use tools.
2. **Skills** auto-activate on PDDL context, inject detailed workflow instructions.
3. **Tool descriptions** tell Claude what each planner supports and when to use it.
4. **settings.json** pre-approves all MCP tools so Claude calls them without friction.

## Plugin Structure

```
pddl-copilot/
├── .claude-plugin/
│   ├── plugin.json            # Plugin metadata
│   └── marketplace.json       # Plugin marketplace catalog
├── .claude/
│   ├── settings.json          # Pre-approved tool permissions
│   └── settings.local.json    # Local dev overrides
├── skills/                    # Auto-discovered by Claude Code
│   ├── pddl-planning/
│   │   └── SKILL.md           # Mandatory planning rules
│   └── pddl-validation/
│       └── SKILL.md           # Mandatory validation rules
├── .mcp.json                  # MCP server config (launches Docker)
├── LICENSE                    # MIT license
├── CLAUDE.md                  # Enforcement rules for Claude
├── scripts/
│   └── launch-server.sh       # Builds image if needed, starts container
├── docker/
│   ├── Dockerfile             # Multi-stage: compile + slim runtime
│   ├── docker-compose.yaml    # Optional manual launch
│   ├── solvers_server_wrapper.py  # MCP server implementation
│   ├── .dockerignore          # Docker build exclusions
│   └── verify.sh              # Smoke test
└── README.md
```

## Smoke Test

After building the image, verify everything works:

```bash
bash docker/verify.sh
```

Or test manually inside the container:

```bash
docker run --rm pddl-sandbox bash -c '
python3 -c "
from pddl_server import classic_planner
domain = \"(define (domain bw) (:predicates (on ?x ?y) (ontable ?x) (clear ?x) (handempty) (holding ?x)) (:action pick-up :parameters (?x) :precondition (and (clear ?x) (ontable ?x) (handempty)) :effect (and (holding ?x) (not (ontable ?x)) (not (clear ?x)) (not (handempty)))) (:action stack :parameters (?x ?y) :precondition (and (holding ?x) (clear ?y)) :effect (and (on ?x ?y) (clear ?x) (handempty) (not (holding ?x)) (not (clear ?y)))))\"
problem = \"(define (problem bw1) (:domain bw) (:objects a b) (:init (ontable a) (ontable b) (clear a) (clear b) (handempty)) (:goal (on a b)))\"
result = classic_planner(domain, problem)
plan, t = result[\"plan\"], result[\"solve_time\"]
print(f\"Plan: {plan} in {t:.2f}s\")
"'
```

## Compatibility

- **macOS** (Intel & Apple Silicon)
- **Linux** (x86_64 & ARM64)
- **Windows** via WSL2
