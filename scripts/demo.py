"""Run the Phase 0 design loop from the CLI and pretty-print the result.

    python -m scripts.demo
    python -m scripts.demo "Make 15 analogs, MW<350, logP 1-3, no PAINS" "c1ccccc1C(=O)O"

Runs fully offline with the mock LLM unless provider keys are configured in .env.
"""
from __future__ import annotations

import asyncio
import sys

from services.agent.orchestrator import DesignOrchestrator

DEFAULT_GOAL = "Make 12 analogs with MW<300, logP 1-3, no PAINS, drug-like"
DEFAULT_SEED = "c1ccccc1C(=O)O"


async def main() -> None:
    goal = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_GOAL
    seed = sys.argv[2] if len(sys.argv) > 2 else DEFAULT_SEED

    result = await DesignOrchestrator().run(goal, seed)

    print(f"\nGoal   : {result.goal}")
    print(f"Parent : {result.parent_smiles}")
    print(f"Models : {result.models_used}\n")
    print("Trace:")
    for t in result.trace:
        print(f"  {t.step}. {t.tool} (v{t.tool_version}) -> {t.summary}")
    print(f"\nCandidates ({sum(c.passed_filters for c in result.candidates)} passed filters):")
    print(f"  {'mod':6} {'smiles':26} {'MW':>7} {'logP':>6} {'QED':>5}  pass")
    for c in result.candidates:
        p = c.properties
        print(
            f"  {c.modification:6} {c.smiles:26} {p['mw']:7} {p['logp']:6} "
            f"{p['qed']:5}  {'✓' if c.passed_filters else '·'}"
        )
    print("\nExplanation:\n  " + result.explanation.replace("\n", "\n  "))


if __name__ == "__main__":
    asyncio.run(main())
