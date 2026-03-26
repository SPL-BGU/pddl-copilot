# PDDL Solver — Plugin Rules

PDDL planning plugin using Fast Downward and Metric-FF in Docker via MCP.

See `skills/pddl-planning/SKILL.md` for tool reference, mandatory workflow, and rules.

## Docker

The pre-built Docker image is pulled from GHCR on first use (~30-60s).
If the pull fails, the plugin falls back to building locally from source (~15 min).
To rebuild manually: `docker build -t pddl-sandbox ../../docker/`

### After pushing changes to `docker/Dockerfile` or `docker/solvers_server_wrapper.py`:
- GitHub Actions automatically builds and pushes a new multi-arch image to `ghcr.io/spl-bgu/pddl-sandbox:latest`
- The GHCR package must have **public visibility** (repo Settings → Packages → pddl-sandbox → Change visibility) for `docker pull` to work without auth
- Users get the updated image on their next session (the launch script re-pulls if no local image exists)
