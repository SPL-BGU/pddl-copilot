# Build & Push Workflow

## Overview

The CI pipeline builds multi-arch Docker images (`linux/amd64` + `linux/arm64`) and publishes them to GitHub Container Registry (GHCR).

Workflow file: `.github/workflows/docker-publish.yml`

## Trigger

- Push to `main` that modifies `docker/Dockerfile` or `docker/solvers_server_wrapper.py`
- Manual trigger via `workflow_dispatch`

## Jobs

### 1. `build-amd64`

- **Runner:** `ubuntu-latest` (native x86_64)
- Builds `linux/amd64` image natively
- Pushes to `ghcr.io/<owner>/pddl-sandbox:build-amd64`
- Uses GHA cache scoped to `amd64`

### 2. `build-arm64`

- **Runner:** `ubuntu-24.04-arm` (native ARM64)
- Builds `linux/arm64` image natively
- Pushes to `ghcr.io/<owner>/pddl-sandbox:build-arm64`
- Uses GHA cache scoped to `arm64`

### 3. `merge`

- **Runner:** `ubuntu-latest`
- Waits for both build jobs to complete
- Runs `docker buildx imagetools create` to combine the two per-arch images into a single multi-arch manifest
- Tags the manifest as `:latest` and `:<commit-sha>`

## Design Decisions

### Native runners instead of QEMU cross-compilation

A single-job approach using QEMU (`docker/setup-qemu-action`) can build both architectures on one `ubuntu-latest` runner. However, QEMU user-mode emulation is significantly slower — compiling C/C++ solvers (Fast Downward, Metric-FF, VAL) under emulation can take 30+ minutes.

Splitting into native runners (`ubuntu-latest` for amd64, `ubuntu-24.04-arm` for arm64) builds each arch at full speed and in parallel. The `ubuntu-24.04-arm` runner is available for free on public GitHub repos.

### Intermediate per-arch tags

Each build job pushes to a temporary tag (`build-amd64`, `build-arm64`). These are required so the `merge` job can reference the per-arch images when creating the multi-arch manifest. They are overwritten on every run and are not intended for end-user consumption.

### `provenance: false`

Build provenance attestations (enabled by default in `docker/build-push-action` v6) create OCI image indexes instead of plain manifests. `docker buildx imagetools create` cannot merge image indexes into a multi-arch manifest. Disabling provenance on the per-arch builds ensures they push plain manifests that can be merged cleanly.

### Separate cache scopes

Each arch job uses its own GHA cache scope (`scope=amd64` / `scope=arm64`). Without separate scopes, the two jobs would compete for the same cache key space and repeatedly evict each other's layers.

### Compatibility

The final multi-arch manifest is functionally identical to what a single-job QEMU build produces. `docker pull` resolves to the correct arch automatically:

| Platform | Arch pulled |
|---|---|
| macOS (Apple Silicon) | `linux/arm64` |
| macOS (Intel) | `linux/amd64` |
| Linux (x86_64) | `linux/amd64` |
| Linux (aarch64) | `linux/arm64` |
| WSL on Windows (x86_64) | `linux/amd64` |
