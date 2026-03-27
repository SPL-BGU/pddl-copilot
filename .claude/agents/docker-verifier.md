---
name: docker-verifier
description: Runs Docker smoke tests for a plugin. Builds the image and runs verify.sh. Use after Docker or MCP server changes.
tools: Bash, Read, Grep
model: haiku
maxTurns: 8
---

Run Docker verification for a plugin. Default target: both `plugins/pddl-solver` and `plugins/pddl-validator`.

1. Check Docker is running: `docker info`
2. Build the image: `docker build -t pddl-sandbox docker/`
3. Run smoke tests: `bash plugins/pddl-solver/tests/verify.sh` and `bash plugins/pddl-validator/tests/verify.sh`
4. Report results:
   - Build: success/failure (with error excerpt if failed)
   - Each smoke test: pass/fail
   - Image size: `docker images pddl-sandbox --format "{{.Size}}"`

If a specific plugin is mentioned in the task, adjust paths accordingly:
- Verify script: `plugins/<plugin-name>/tests/verify.sh`

If no verify.sh exists for the target plugin, report that and suggest creating one following the pddl-solver pattern.
