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

import argparse
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
        "MEASURED AND FAILING, not merely unmeasured. Re-docking into PDB 1HSG recovers "
        "the crystal pose during sampling (0.85 A) but the scoring function ranks a "
        "4.73 A pose first, above the 2.0 A criterion — so the pose a user actually gets "
        "is the wrong binding mode. Improving it most likely means better receptor "
        "preparation (a dedicated tool rather than OpenBabel, and retaining the conserved "
        "flap water) rather than a different engine"
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

#: Capabilities whose tools return the full Prediction envelope (value + uncertainty +
#: applicability domain + provenance, hence a ModelKind). The Unvalidated section of
#: VALIDATION.md makes this exact claim in prose, so the claim lives here as data and
#: tests/test_prediction_contract.py checks it against the live tools. A predictor that
#: gains or loses the envelope fails that test until this set and the prose agree again.
PREDICTORS_RETURNING_MODEL_KIND: frozenset[str] = frozenset(
    {
        "ADMET — aqueous solubility (logS)",
        "ADMET — logD7.4",
        "ADMET — hERG liability",
        "ADMET — CYP3A4 substrate likelihood",
        "ADMET — metabolic stability",
        "ADMET — plasma protein binding",
        "ADMET — blood-brain barrier penetration",
        "Synthetic accessibility (SA score)",
        "Docking — re-docking a crystallographic pose",
    }
)


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
    # PASSING results only. A benchmark that ran and failed does not make its
    # capability validated, and excluding it from the Unvalidated table on the strength
    # of having been measured would be precisely the wrong reading.
    validated = {r["capability"] for r in results if r["passed"]}

    lines: list[str] = [
        "# Validation",
        "",
        "<!-- GENERATED FILE — DO NOT EDIT BY HAND.",
        "     Produced by `python -m tests.validation.report` from a run of the",
        "     validation suite. CI (.github/workflows/validation.yml) runs",
        "     `report.py --check`, which fails if any capability measured in the run is",
        "     missing here, if a PASS/FAIL disagrees with what was measured, or if",
        "     anything without a passing benchmark is presented as validated. -->",
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
        "This file carries no generation timestamp on purpose: its content should depend",
        "only on the measurements, and a clock in it would make every run differ from every",
        "other for no reason. Git already records when it changed. For the same reason CI",
        "checks this document structurally rather than by exact diff — AutoDock Vina is",
        "multithreaded and not bit-reproducible even with a fixed seed, so the re-docking",
        "RMSD moves slightly between runs on identical code. What CI does enforce is that",
        "nothing here contradicts what the suite measured.",
    ]

    failed = [r for r in results if not r["passed"]]
    if failed:
        lines += [
            "",
            "---",
            "",
            "## Not currently meeting its criterion",
            "",
            "Stated here, at the top, rather than left to be discovered further down. These",
            "benchmarks run and are measured; they do not meet the success criterion they are",
            "judged against, and the criterion has not been moved to accommodate that.",
            "",
        ]
        for r in sorted(failed, key=lambda x: x["capability"]):
            metrics = ", ".join(f"{k} = {v}" for k, v in r["metrics"].items())
            lines += [f"- **{r['capability']}** — {metrics}. See below for what this means."]
        lines += [""]

    # --- validated ------------------------------------------------------------
    lines += ["", "---", "", "## Benchmark results", ""]
    if not results:
        lines += [
            "> **No validation results were recorded in this run.**",
            "> That is a failure state, not an empty section: it means the suite did not",
            "> run, or ran and produced nothing. Do not read it as 'nothing needed",
            "> validating'.",
            "",
        ]
    for r in sorted(results, key=lambda x: x["capability"]):
        status = (
            "PASS — meets its stated criterion"
            if r["passed"]
            else "**FAIL — does not meet its stated criterion**"
        )
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
        # Per benchmark, not once for the page. Benchmarks are not necessarily
        # measured in the same environment — the docking case only runs where Vina
        # is installed — and a union of their environments describes none of them.
        env = r.get("environment") or {}
        if env:
            bits = ", ".join(f"{k} {v}" for k, v in sorted(env.items()))
            lines += ["", f"_Measured with: {bits}._"]
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
        "The predictors among these — the ADMET endpoints, synthetic accessibility and",
        "docking — return their `ModelKind`, uncertainty and applicability domain in the",
        "API payload, so a caller can tell programmatically what it is looking at without",
        "consulting this page. `PREDICTORS_RETURNING_MODEL_KIND` in tests/validation/",
        "report.py records that set and tests/test_prediction_contract.py checks it against",
        "the live tools, so this sentence fails a build rather than drifting.",
        "",
        "The remaining entries do not carry that payload, and the distinction is real rather",
        "than an omission: the rule battery, the structural-alert catalogues and the MPO",
        "desirability function are not predictions. They are definitions — a Lipinski",
        "violation is not an estimate of anything, and the MPO score encodes a stated",
        "preference with no ground truth to be uncertain about. Retrosynthesis returns",
        "disconnections rather than a number. Wrapping any of them in a prediction envelope",
        "would suggest an error bar where there is nothing to be wrong about.",
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


def check(results: list[dict]) -> list[str]:
    """Verify the committed document is consistent with this run. Returns problems.

    Deliberately NOT a byte-for-byte diff against a freshly rendered document, and the
    reason is specific: AutoDock Vina is multithreaded and is not bit-reproducible even
    with a fixed seed, so the re-docking RMSD moves between runs on identical code
    (4.22 A and 4.73 A were both measured while investigating one change). A byte diff
    would therefore fail constantly for reasons that have nothing to do with the
    document being wrong, and a gate that cries wolf gets switched off.

    What is checked instead is everything that MATTERS about the document being honest:

      - every capability measured in this run appears in the document;
      - every capability's PASS/FAIL status in the document matches the run;
      - a capability whose benchmark failed is not presented as validated;
      - every capability in the inventory with no passing result is listed as
        unvalidated.

    A stale decimal place is a cosmetic problem. A capability described as validated
    when its benchmark is failing is a false claim, and that is what this catches.
    """
    problems: list[str] = []
    if not OUTPUT.exists():
        return [f"{OUTPUT} does not exist; run `make validate`"]
    doc = OUTPUT.read_text()

    for r in results:
        capability = r["capability"]
        if capability not in doc:
            problems.append(
                f"measured capability {capability!r} is missing from {OUTPUT.name}"
            )
            continue
        # Locate this capability's section and read the status line inside it.
        section = doc.split(f"### {capability}", 1)
        if len(section) < 2:
            problems.append(f"{capability!r} has no section heading in {OUTPUT.name}")
            continue
        body = section[1].split("\n### ", 1)[0]
        says_pass = "**Status:** PASS" in body
        says_fail = "**Status:** **FAIL" in body
        if r["passed"] and not says_pass:
            problems.append(f"{capability!r} passed in this run but is not shown as PASS")
        if not r["passed"]:
            if not says_fail:
                problems.append(
                    f"{capability!r} FAILED its criterion in this run but "
                    f"{OUTPUT.name} does not say so"
                )
            # The stronger check: a failing benchmark must also appear in the
            # Unvalidated table. Being measured is not being validated.
            unvalidated_table = doc.split("## Unvalidated", 1)
            if len(unvalidated_table) < 2 or capability not in unvalidated_table[1]:
                problems.append(
                    f"{capability!r} failed its benchmark but is not listed under "
                    f"'Unvalidated' — a measured failure is not a validation"
                )

    passing = {r["capability"] for r in results if r["passed"]}
    unvalidated_section = doc.split("## Unvalidated", 1)
    for capability in CAPABILITY_INVENTORY:
        if capability in passing:
            continue
        if len(unvalidated_section) < 2 or capability not in unvalidated_section[1]:
            problems.append(
                f"{capability!r} has no passing benchmark but is absent from the "
                f"Unvalidated table"
            )
    return problems


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate or check docs/VALIDATION.md")
    parser.add_argument(
        "--check",
        action="store_true",
        help="verify the committed document is consistent with the recorded results",
    )
    args = parser.parse_args()

    results = _load_results()

    if args.check:
        problems = check(results)
        if problems:
            print(f"{OUTPUT} is inconsistent with the validation run:")
            for problem in problems:
                print(f"  - {problem}")
            print("\nRun `make validate` and commit the regenerated document.")
            return 1
        print(
            f"{OUTPUT.name} is consistent with {len(results)} recorded result(s): "
            f"every measured capability is present, every PASS/FAIL matches, and "
            f"nothing without a passing benchmark is presented as validated"
        )
        return 0

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(render(results))
    print(f"wrote {OUTPUT} from {len(results)} recorded result(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
