# Phase 0 image for the API and the Celery worker (same image, different command).
# RDKit wheels need a few shared libs not in -slim. The docker CLI is inert by default
# (the default + prod stacks mount no socket); it is only exercised by the OPT-IN
# docker-compose.tools.yml overlay, which mounts docker.sock so the worker can launch
# sandboxed CONTAINER tools (docker-out-of-docker) on a trusted single-tenant host (GS-M3).
FROM python:3.13-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
        libxrender1 libxext6 libsm6 docker-cli \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY pyproject.toml ./
COPY apps ./apps
COPY services ./services
COPY scripts ./scripts

RUN pip install --no-cache-dir -e .

EXPOSE 8000
CMD ["uvicorn", "apps.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
