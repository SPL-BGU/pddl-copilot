# Branch Testing

How to validate branch changes on another machine before merging.

## Clone the branch

```bash
git clone -b <branch-name> https://github.com/SPL-BGU/pddl-copilot.git
cd pddl-copilot
```

## Install per tool

**Claude Code** (use `--plugin-dir`, since `/plugins` marketplace search reads from main):
```bash
claude --plugin-dir ./plugins/pddl-solver
```

**Cursor:**
```bash
bash install_marketplace.sh --tool cursor --install
```

**Antigravity:**
```bash
bash install_marketplace.sh --tool antigravity --install
```

The installer resolves absolute paths from wherever you cloned, so it works regardless of branch.

## Smoke Test

```bash
# Static checks (no Docker)
bash tests/static_checks.sh

# Plugin tests (Docker required)
bash plugins/pddl-solver/tests/verify.sh
bash plugins/pddl-validator/tests/verify.sh

# MCP protocol test (Docker required)
bash tests/mcp_protocol_test.sh
```
