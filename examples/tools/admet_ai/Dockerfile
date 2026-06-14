# Real ADMET backend container tool — ADMET-AI (pretrained Chemprop-RDKit GNN).
# Build:
#   docker build -t glowsky-tool-admet-ai:0.1.0 examples/tools/admet_ai
#
# Python 3.11 (best torch/chemprop wheel coverage). The install is large (torch); it is
# STAGED across layers so a flaky/slow network only re-downloads the failed layer on
# rebuild (pip does NOT retry hash-mismatch/corruption errors, so big single installs
# are fragile). Model weights are warmed into a layer so inference runs offline.
FROM python:3.11-slim

# Build tools + git: some transitive deps (e.g. descriptastorus) may build from source.
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential git \
    && rm -rf /var/lib/apt/lists/*

ENV PIP_DEFAULT_TIMEOUT=600 PIP_RETRIES=12

# Stage 0: a newer pip handles flaky downloads better than the bundled 24.0.
RUN pip install --no-cache-dir --upgrade pip

# Stage 1: torch alone (the heavy wheel) -> cached once it succeeds, so admet-ai
# failures below never re-download it.
RUN pip install --no-cache-dir torch

# Stage 2: ADMET-AI (torch already satisfied -> a much smaller remaining download).
RUN pip install --no-cache-dir admet-ai

# Stage 3: warm-up the model so its weights are baked into the image -> the sandbox
# runs with NO network at execution time (--network none).
RUN python -c "from admet_ai import ADMETModel; ADMETModel()"

WORKDIR /tool
COPY tool.py .

ENTRYPOINT ["python", "tool.py"]
