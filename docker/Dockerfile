# ===========================================================================
# Dockerfile — PDDL Copilot Sandbox
#
# Stage 1: Compile Fast Downward, Metric-FF, and VAL
# Stage 2: Slim runtime with compiled binaries + lightweight MCP server
#
# Build:   docker build -t pddl-sandbox .
# Verify:  bash verify.sh
# ===========================================================================

# --- Planner versions (override at build time with --build-arg) ---
ARG FD_TAG=release-24.06.1
ARG MFF_COMMIT=543cb367a44a
ARG VAL_COMMIT=3c7a1f330bda

# ===== Stage 1: Builder =====
FROM ubuntu:22.04 AS builder
ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y \
    build-essential cmake git python3 python3-pip flex bison \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build

# Re-declare ARGs after FROM (global ARGs need re-declaration per stage)
ARG FD_TAG
ARG MFF_COMMIT
ARG VAL_COMMIT

# --- Fast Downward ---
RUN git clone --depth 1 --branch ${FD_TAG} https://github.com/aibasel/downward.git FastDownward \
    && cd FastDownward \
    && python3 build.py \
    && (strip --strip-unneeded builds/release/bin/downward 2>/dev/null || true)

# --- Metric-FF ---
RUN git clone https://github.com/HenryKautz/Metric-FF.git METRIC_FF \
    && cd METRIC_FF \
    && git checkout ${MFF_COMMIT} \
    && make CFLAGS="-O3 -w -fcommon -Wno-error -Wno-implicit-function-declaration -Wno-int-conversion" LFLAGS="-O3 -fcommon -g" \
    && (strip ff 2>/dev/null || true)

# --- VAL ---
RUN git clone https://github.com/KCL-Planning/VAL.git VAL \
    && cd VAL && git checkout ${VAL_COMMIT} \
    && mkdir build && cd build \
    && cmake -DCMAKE_BUILD_TYPE=Release -DCMAKE_INSTALL_PREFIX=/build/VAL/install .. \
    && make -j"$(nproc)" \
    && make install \
    && (strip /build/VAL/install/bin/* 2>/dev/null || true)


# ===== Stage 2: Runtime =====
FROM ubuntu:22.04
ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y --no-install-recommends \
    python3 python3-pip libstdc++6 \
    && rm -rf /var/lib/apt/lists/*

# --- Copy compiled planners (only runtime files, not full repos) ---
COPY --from=builder /build/FastDownward/fast-downward.py  /opt/planners/FastDownward/
COPY --from=builder /build/FastDownward/driver/           /opt/planners/FastDownward/driver/
COPY --from=builder /build/FastDownward/builds/           /opt/planners/FastDownward/builds/
COPY --from=builder /build/METRIC_FF                      /opt/planners/METRIC_FF
COPY --from=builder /build/VAL/install/bin/               /opt/planners/VAL/

# --- Install MCP server dependency ---
RUN pip3 install --no-cache-dir mcp

# --- Copy MCP server ---
COPY solvers_server_wrapper.py /opt/server/pddl_server.py
ENV PYTHONPATH="/opt/server"

# --- Verify import works ---
RUN python3 -c "from pddl_server import validate_pddl_syntax, get_state_transition; print('MCP tools import OK')"

WORKDIR /workspace

ARG FD_TAG
ARG MFF_COMMIT
ARG VAL_COMMIT
LABEL org.opencontainers.image.description="PDDL sandbox with Fast Downward, Metric-FF, and VAL"
LABEL pddl.fd.tag="${FD_TAG}"
LABEL pddl.mff.commit="${MFF_COMMIT}"
LABEL pddl.val.commit="${VAL_COMMIT}"
