# Experiments — Reproducing "Toward PDDL Planning Copilot"

Reproduction of the evaluation from [Benyamin et al., 2025 (arXiv:2509.12987)](https://arxiv.org/abs/2509.12987).

Tests Ollama LLMs **with** and **without** MCP planning tools on 5 PDDL tasks:

| Task | Description |
|------|-------------|
| `solve` | Find a plan for a domain + problem |
| `validate_domain` | Check domain PDDL syntax |
| `validate_problem` | Check problem PDDL syntax |
| `validate_plan` | Verify a given plan is correct |
| `simulate` | Produce a state-transition trace |

## Prerequisites

- **Docker** running (the MCP planning server runs in Docker)
- **Ollama** installed and running with desired models pulled
- **Python 3.10+**

```bash
# Pull models used in the paper
ollama pull qwen3:0.5b
ollama pull qwen3:4b
```

## Setup

```bash
cd experiments
pip3 install -r requirements.txt
```

## Running

### Basic run (single-task evaluation)

```bash
python3 run_experiment.py --models qwen3:0.5b qwen3:4b
```

### Run a specific task only

```bash
python3 run_experiment.py --models qwen3:4b --tasks solve validate_plan
```

### Include multi-task chain evaluation

```bash
python3 run_experiment.py --models qwen3:4b --chains --chain-samples 20
```

### All options

```
--models          Ollama model names (default: qwen3:0.5b qwen3:4b)
--tasks           Tasks to evaluate (default: all 5)
--domains-dir     Path to domains directory (default: ./domains)
--output-dir      Path to save result JSON files (default: ./results)
--num-variants    Prompt variants per task (default: 5, as in the paper)
--temperature     LLM temperature (default: 0.0, as in the paper)
--chains          Also run multi-task chain evaluation
--chain-samples   Samples per chain length (default: 20)
--seed            Random seed for chain sampling (default: 42)
```

## Output

Results are saved as JSON in `results/`:

- `single_task_<timestamp>.json` — per-instance results with model response, tool calls, success flag, and timing
- `chain_<timestamp>.json` — chain evaluation success rates per model and chain length

A summary table (reproducing Table 1 from the paper) is printed to stdout.

## Adding Domains

The paper evaluates 10 domains. This repo includes 3 sample domains for quick testing. To add more IPC benchmark domains:

1. Create a directory under the appropriate type:
   ```
   domains/classical/<domain-name>/domain.pddl
   domains/classical/<domain-name>/p01.pddl
   domains/classical/<domain-name>/p02.pddl
   ...
   ```
   or for numeric:
   ```
   domains/numeric/<domain-name>/domain.pddl
   domains/numeric/<domain-name>/p01.pddl
   ...
   ```

2. The script auto-discovers all domains at runtime.

### Domains from the paper

| Type | Domain | Source |
|------|--------|--------|
| Classical | barman, blocksworld, depots, rovers, satellite | IPC benchmarks |
| Numeric | depots-numeric, counters, farmland, sailing | 2023 Numeric IPC track |
| Numeric | minecraft-pogo | Non-IPC |

IPC benchmarks are available at: https://github.com/aibasel/downward-benchmarks

## How It Works

1. **Ground truth** — the MCP planners (Fast Downward, Metric-FF, VAL) solve all problems as oracle
2. **With-tools condition** — model gets MCP tool descriptions and can call them via Ollama's tool-calling API
3. **Without-tools condition** — model must answer on its own (baseline)
4. **Success criteria** — with-tools: did the model call the correct tool? Without-tools: does the response match ground truth?
5. **Chain evaluation** — random sequences of n tasks in a single conversation, all must succeed
