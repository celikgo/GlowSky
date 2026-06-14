# Docking-enabled image: the API/worker image plus a real AutoDock Vina + OpenBabel
# toolchain, so the adapter-gated `dock` tool runs for real (GLOWSKY_DOCKING_BACKEND=vina).
#
# Pinned to linux/amd64: AutoDock Vina ships official binaries for x86_64 only, so on
# Apple Silicon this image runs under Docker's emulation. It's opt-in (see
# docker-compose.docking.yml) precisely so the default native stack stays fast.
FROM --platform=linux/amd64 python:3.13-slim

# RDKit needs a few shared libs (-slim lacks them); openbabel provides `obabel` for
# ligand PDB->PDBQT prep; curl/ca-certificates fetch the Vina binary.
RUN apt-get update && apt-get install -y --no-install-recommends \
        libxrender1 libxext6 libsm6 openbabel ca-certificates curl \
    && rm -rf /var/lib/apt/lists/*

# AutoDock Vina — official static release binary, validated at build time.
ARG VINA_VERSION=1.2.5
RUN curl -fsSL -o /usr/local/bin/vina \
        "https://github.com/ccsb-scripps/AutoDock-Vina/releases/download/v${VINA_VERSION}/vina_${VINA_VERSION}_linux_x86_64" \
    && chmod +x /usr/local/bin/vina \
    && vina --version \
    && obabel -V

WORKDIR /app
COPY pyproject.toml ./
COPY apps ./apps
COPY services ./services
COPY scripts ./scripts

RUN pip install --no-cache-dir -e .

EXPOSE 8000
CMD ["uvicorn", "apps.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
