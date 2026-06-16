# Build:
#   docker build -t glowsky-tool-cargo-dimensioning:0.1.0 examples/tools/cargo_dimensioning
# Pure-stdlib deterministic tool — no third-party deps, no network (the caller enforces
# --network none / --read-only / non-root).
FROM python:3.13-slim

WORKDIR /tool
COPY tool.py .

# The ABI: read JSON on stdin, emit JSON on stdout.
ENTRYPOINT ["python", "tool.py"]
