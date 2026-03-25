# Bash Scripts

## `docker/verify.sh`

Smoke-tests the `pddl-sandbox` Docker image by exercising every solver function exposed by the MCP server.

### Usage

```bash
./docker/verify.sh              # tests the default "pddl-sandbox" image
./docker/verify.sh my-image:tag # tests a specific image
```

### What it tests

The script runs five checks, each in an isolated `docker run --rm` container:

| # | Test | What it validates |
|---|---|---|
| 1 | Server imports | All five functions (`classic_planner`, `numeric_planner`, `validate_pddl_syntax`, `save_plan`, `get_state_transition`) are importable |
| 2 | `classic_planner` | Fast Downward solves a blocksworld problem and returns a plan |
| 3 | `validate_pddl_syntax` | VAL parses and checks a domain + problem |
| 4 | `save_plan` | A plan list is written to disk as a `.solution` file |
| 5 | `get_state_transition` | End-to-end: solve, save, then simulate the plan to produce a state trace |

### Flow

1. A blocksworld domain and problem are defined inline as shell variables
2. Each test spins up a fresh container, writes the PDDL files inside it, and calls the relevant Python function
3. Output is checked with `grep` — a match prints `OK` (green), no match prints `FAILED` (red)
4. The script uses `set -euo pipefail` but individual tests are guarded by `if`, so all five run regardless of earlier failures
