#!/usr/bin/env bash
# launch-server.sh — Called by .mcp.json at plugin load.
#
# 1. Checks if Docker is installed
# 2. Pulls the pre-built image from GHCR (fast, ~30-60s)
#    Falls back to local build if pull fails (~15 min, first time only)
# 3. Runs the MCP server inside the container via stdio
#
# The container stays alive for the duration of the Claude Code session.
# stdin/stdout are piped to Claude Code (MCP stdio transport).

set -euo pipefail

REGISTRY_IMAGE="ghcr.io/spl-bgu/pddl-sandbox:latest"
LOCAL_IMAGE="pddl-sandbox"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PLUGIN_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
DOCKER_DIR="$PLUGIN_ROOT/docker"

# --- 1. Docker installed and daemon ready? ---
if ! command -v docker &>/dev/null; then
    echo '{"error": "Docker is not installed. Get it from https://docker.com"}' >&2
    exit 1
fi

# Wait for Docker daemon to be responsive (handles Docker Desktop slow startup)
MAX_WAIT=30
for i in $(seq 1 $MAX_WAIT); do
    if docker info &>/dev/null; then
        break
    fi
    if [ "$i" -eq 1 ]; then
        echo "[pddl-copilot] Waiting for Docker daemon to start..." >&2
    fi
    if [ "$i" -eq $MAX_WAIT ]; then
        echo "[pddl-copilot] Docker daemon not responding after ${MAX_WAIT}s. Is Docker Desktop running?" >&2
        exit 1
    fi
    sleep 1
done

# --- 2. Resolve image: prefer GHCR pull, fall back to local build ---
IMAGE=""

# Check if registry image exists locally already
if docker image inspect "$REGISTRY_IMAGE" &>/dev/null; then
    IMAGE="$REGISTRY_IMAGE"
else
    # Try pulling from GHCR
    echo "[pddl-copilot] Pulling pre-built image from GHCR..." >&2
    if docker pull "$REGISTRY_IMAGE" >&2 2>&1; then
        IMAGE="$REGISTRY_IMAGE"
        echo "[pddl-copilot] Image ready." >&2
    else
        echo "[pddl-copilot] GHCR pull failed. Falling back to local build..." >&2
    fi
fi

# Fallback: local build (version-tagged)
if [ -z "$IMAGE" ]; then
    VERSION_HASH=$(cat "$DOCKER_DIR/Dockerfile" "$DOCKER_DIR/solvers_server_wrapper.py" | shasum -a 256 | cut -c1-12)
    LOCAL_TAGGED="${LOCAL_IMAGE}:${VERSION_HASH}"

    if ! docker image inspect "$LOCAL_TAGGED" &>/dev/null; then
        echo "[pddl-copilot] Building PDDL sandbox image locally (version ${VERSION_HASH})..." >&2
        echo "[pddl-copilot] This compiles Fast Downward, Metric-FF, and VAL (~15 min on first build)." >&2
        docker build -t "$LOCAL_TAGGED" "$DOCKER_DIR" >&2
        # Clean up old local versions
        old_images=$(docker images --format '{{.Repository}}:{{.Tag}}' | grep "^${LOCAL_IMAGE}:" | grep -v ":${VERSION_HASH}$" || true)
        if [ -n "$old_images" ]; then
            echo "[pddl-copilot] Removing old image versions..." >&2
            for old_img in $old_images; do
                docker ps -a -q --filter "ancestor=$old_img" 2>/dev/null | xargs -r docker rm -f 2>/dev/null >&2 || true
                docker rmi "$old_img" 2>/dev/null >&2 || true
            done
        fi
        echo "[pddl-copilot] Image ready." >&2
    fi
    IMAGE="$LOCAL_TAGGED"
fi

# --- 3. Launch the MCP server inside the container ---
# -i            : keep stdin open (required for MCP stdio transport)
# --rm          : remove container when session ends
# -v            : mount the user's working directory so planner can access PDDL files
# The server reads from stdin, writes to stdout — MCP stdio protocol.
exec docker run --rm -i \
    -e "HOST_PWD=${PWD}" \
    -v "${PWD}:/workspace" \
    -w /workspace \
    "${IMAGE}" \
    python3 -m pddl_server
