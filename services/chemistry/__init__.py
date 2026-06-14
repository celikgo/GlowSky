"""Deterministic chemistry core. Nothing trusts an LLM-emitted structure until it
passes through validation here. The agent reaches chemistry ONLY via the tool
execution service (services.tools).
"""

# Bump when tool behaviour changes — recorded in provenance for reproducibility.
CHEM_TOOLS_VERSION = "0.1.0"
