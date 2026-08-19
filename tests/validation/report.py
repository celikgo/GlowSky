"""Generate docs/VALIDATION.md from a validation run.

The document is GENERATED, never hand-written. A validation page maintained by hand
drifts from the code it describes within a release or two, and a stale validation
claim is worse than no validation page at all — it is a specific false statement about
accuracy, published under the project's name.

Run:  python -m tests.validation.report
CI:   .github/workflows/validation.yml runs the suite, then this, then fails if the
      committed docs/VALIDATION.md differs from what the run produced.

The document has two halves and the second one is the point. Anyone can publish the
benchmarks they passed. The `UNVALIDATED` table lists every predictive capability in
Glowsky that has NO benchmark behind it, so a reader can tell at a glance which
numbers have been checked against the world and which have only been checked against
this project's own intentions.
"""
from __future__ import annotations

import json

from tests.validation._harness import RESULTS_PATH, ROOT

OUTPUT = ROOT / "docs" / "VALIDATION.md"

#: Every predictive capability Glowsky exposes, and what would have to exist to
#: validate it. Anything here without a matching entry in the results file is
#: published as UNVALIDATED.
#:
#: tests/validation/test_inventory_is_complete.py fails if a predictive tool is added
#: to the catalog without being listed here — so this cannot silently fall behind the
#: code, which is the usual way a document like this becomes a lie.
CAPABILITY_INVENTORY: dict[str, str] = {
    "ADMET — aqueous solubility (logS)": (
        "validated against Delaney's measured solubilities"
    ),
    "Docking — re-docking a crystallographic pose": (
        "validated by re-docking into PDB 1HSG"
    ),
    "ADMET — logD7.4": (
        "would need a measured logD set (e.g. a public lipophilicity benchmark). "
        "The current model has no ionization term at all, so it cannot be right for "
        "any acid or base"
    ),
    "ADMET — hERG liability": (
        "would need measured hERG IC50 data. Currently a two-term correlation on "
        "lipophilicity and a basic amine"
    ),
    "ADMET — CYP3A4 substrate likelihood": (
        "would need a measured CYP3A4 substrate/non-substrate set"
    ),
    "ADMET — metabolic stability": (
        "would need measured microsomal clearance, per species and matrix. The current "
        "output maps to no experimental unit"
    ),
    "ADMET — plasma protein binding": (
        "would need measured fraction-bound data, and a model that can resolve the "
        "99%-99.9% region where the decisions actually are"
    ),
    "ADMET — blood-brain barrier penetration": (
        "would need a measured CNS penetration set. The current rule models passive "
        "diffusion only and knows nothing about P-gp efflux"
    ),
    "Docking — binding affinity from the Vina score": (
        "NOT VALIDATED AND NOT CLAIMED. A Vina score is not a binding affinity. "
        "Validating an affinity claim would need measured Kd/Ki for a congeneric "
        "series, and Glowsky does not present the score as an affinity anywhere"
    ),
    "Synthetic accessibility (SA score)": (
        "would need expert-assigned synthesizability rankings of the kind Ertl & "
        "Schuffenhauer used. Reproduces the published algorithm via RDKit Contrib; "
        "the algorithm is not re-derived here"
    ),
    "Retrosynthesis — template disconnections": (
        "would need a reaction-route benchmark with expert-validated routes. The "
        "current implementation is a small hand-written template set and finds only "
        "one-step disconnections it already knows"
    ),
    "MPO desirability score": (
        "not a predictive model — a weighted desirability function over descriptors. "
        "There is no ground truth to validate it against; it encodes a preference, "
        "and the preference is the thing being expressed"
    ),
    "Med-chem rule battery (Lipinski, Veber, Ghose, Egan, Muegge, Ro3)": (
        "deterministic threshold rules reproducing published criteria. "
        "tests/test_medchem.py checks the thresholds against the published values; "
        "there is no accuracy to measure because the rules ARE the definition"
    ),
    "Structural alerts (PAINS, BRENK)": (
        "deterministic substructure matching against RDKit's published catalogues. "
        "Exact by construction; what a match MEANS is the uncertain part, and that is "
        "not something a benchmark can settle"
    ),
}


def _load_results() -> list[dict]:
    if not RESULTS_PATH.exists():
        return []
    return json.loads(RESULTS_PATH.read_text())


def _fmt_metric(name: str, value: float, gate: str | None) -> str:
    # A gate like "|x| <= 0.35" contains the character that delimits markdown table
    # cells, and would silently split the row into extra columns.
    #
    # Escaped on a separate line rather than inline in the f-string: a backslash inside
    # an f-string expression is Python 3.12+ syntax, and this repository supports 3.11,
    # where it is a hard SyntaxError. Caught by ruff's target-version = "py311".
    escaped = gate.replace("|", "\\|") if gate else None
    gate_txt = f"`{escaped}`" if escaped else "—"
    return f"| `{name}` | {value} | {gate_txt} |"


def render(results: list[dict]) -> str:
    validated = {r["capability"] for r in results}

    env_bits = set()
    for r in results:
        for k, v in (r.get("environment") or {}).items():
            env_bits.add(f"{k} {v}")

    lines: list[str] = [
        "# Validation",
        "",
        "<!-- GENERATED FILE — DO NOT EDIT BY HAND.",
        "     Produced by `python -m tests.validation.report` from a run of the",
        "     validation suite, and checked in CI (.github/workflows/validation.yml),",
        "     which fails if this file disagrees with what the suite actually measured. -->",
        "",
        "This page reports how Glowsky's predictive components compare against **published**",
        "reference values — measurements and results whose author is somebody other than this",
        "project. It is generated from a run of `tests/validation/`, so every number below was",
        "produced by code in this repository at the commit that generated it.",
        "",
        "**The second table is the important one.** Publishing the benchmarks you pass is easy.",
        "The `Unvalidated` table lists every predictive capability with no benchmark behind it,",
        "so a reader can tell which numbers have been checked against the world and which have",
        "only been checked against this project's own intentions.",
        "",
        "This file carries no generation timestamp on purpose. CI regenerates it and fails",
        "if the result differs from what is committed, so its content must depend only on",
        "the measurements — a clock in the file would make every run differ from every",
        "other. Git already records when it changed.",
    ]
    if env_bits:
        lines += ["", f"_Environment: {', '.join(sorted(env_bits))}._"]

    # --- validated ------------------------------------------------------------
    lines += ["", "---", "", "## Validated against published reference values", ""]
    if not results:
        lines += [
            "> **No validation results were recorded in this run.**",
            "> That is a failure state, not an empty section: it means the suite did not",
            "> run, or ran and produced nothing. Do not read it as 'nothing needed",
            "> validating'.",
            "",
        ]
    for r in sorted(results, key=lambda x: x["capability"]):
        status = "PASS" if r["passed"] else "**FAIL**"
        lines += [
            f"### {r['capability']}",
            "",
            f"- **Status:** {status}",
            f"- **Model under test:** {r['model']}",
            f"- **Benchmark:** {r['benchmark']} (_n_ = {r['n']})",
            f"- **Reference source:** {r['source']}",
            f"  <{r['source_url']}>",
            "",
            "| metric | measured | gate |",
            "|---|---|---|",
        ]
        gates = r.get("gates") or {}
        for name, value in r["metrics"].items():
            lines.append(_fmt_metric(name, value, gates.get(name)))
        if r.get("notes"):
            lines += ["", f"> **What this does not show.** {r['notes']}"]
        lines.append("")

    # --- unvalidated ----------------------------------------------------------
    lines += [
        "---",
        "",
        "## Unvalidated",
        "",
        "These capabilities are shipped and are **not** validated against any published",
        "reference. They are listed here rather than beside the validated ones because a",
        "uniform panel of numbers is precisely how an in-house heuristic ends up being read",
        "as a measurement. Each entry says what a real validation would require.",
        "",
        "Every one of these returns its `ModelKind` in the API payload, so a caller can tell",
        "programmatically which of these it is looking at without consulting this page.",
        "",
        "| capability | what validating it would take |",
        "|---|---|",
    ]
    for capability, requirement in sorted(CAPABILITY_INVENTORY.items()):
        if capability in validated:
            continue
        lines.append(f"| {capability} | {requirement} |")

    lines += [
        "",
        "---",
        "",
        "## What none of this is",
        "",
        "Every number Glowsky produces is a **triage and prioritisation aid**: something to",
        "help decide which compound to make next. Specifically, and regardless of how good a",
        "benchmark result above looks:",
        "",
        "- **A prediction is not a measurement.** The solubility model's own error bar is",
        "  about one log unit — a factor of ten in concentration.",
        "- **A docking score is not a binding affinity.** Vina's score is a scoring-function",
        "  value. Recovering a crystal pose is evidence about *geometry*, and says nothing",
        "  about the strength of binding.",
        "- **None of this is a regulatory or safety assessment.** A predicted hERG risk is a",
        "  structural flag for follow-up, not a cardiac safety finding.",
        "- **Out-of-domain values are not usable.** Where a molecule falls outside a model's",
        "  applicability domain, the prediction carries a `caveat` field in the payload and",
        "  is reported for transparency only.",
        "",
        "## Reproducing this",
        "",
        "```bash",
        "make validate          # run the validation suite and regenerate this file",
        "```",
        "",
        "The re-docking benchmark needs AutoDock Vina and OpenBabel on `PATH`; without them",
        "it skips locally. In CI it cannot skip — `.github/workflows/validation.yml` sets",
        "`GLOWSKY_REQUIRE_DOCKING=1`, which turns a skip into a failure.",
        "",
        "Reference values and their provenance live in `tests/validation/reference/`. Every",
        "file there carries a header naming its source, how it was obtained, and what is and",
        "is not claimed about it.",
        "",
    ]
    return "\n".join(lines)


def main() -> None:
    results = _load_results()
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(render(results))
    print(f"wrote {OUTPUT} from {len(results)} recorded result(s)")


if __name__ == "__main__":
    main()
