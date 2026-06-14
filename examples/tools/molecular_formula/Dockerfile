# Example container tool image. Build:
#   docker build -t glowsky-tool-molecular-formula:0.1.0 examples/tools/molecular_formula
FROM python:3.13-slim

RUN pip install --no-cache-dir "rdkit>=2024.3"

WORKDIR /tool
COPY tool.py .

# The ABI: read JSON on stdin, emit JSON on stdout. No network, non-root, read-only FS
# are enforced by the caller (ContainerRuntime), not here.
ENTRYPOINT ["python", "tool.py"]
