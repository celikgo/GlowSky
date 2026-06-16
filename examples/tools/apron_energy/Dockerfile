# Build:
#   docker build -t glowsky-tool-apron-energy:0.1.0 examples/tools/apron_energy
# Pure-stdlib deterministic projection — no third-party deps, no network.
FROM python:3.13-slim

WORKDIR /tool
COPY tool.py .

# The ABI: read JSON on stdin, emit JSON on stdout.
ENTRYPOINT ["python", "tool.py"]
