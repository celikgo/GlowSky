# Build:
#   docker build -t glowsky-tool-damage-detect:0.1.0 examples/tools/damage_detect
# Pure-stdlib deterministic gate — no third-party deps, no network.
FROM python:3.13-slim

WORKDIR /tool
COPY tool.py .

# The ABI: read JSON on stdin, emit JSON on stdout.
ENTRYPOINT ["python", "tool.py"]
