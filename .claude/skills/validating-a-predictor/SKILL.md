---
name: validating-a-predictor
description: Use when adding, changing or auditing anything that predicts a number — an ADMET endpoint, a docking adapter, a scoring function, a synthesizability model, a new chemistry tool that estimates rather than computes. Covers the prediction envelope (uncertainty, applicability domain, provenance with a Crossref-resolvable DOI), the capability inventory, the benchmark harness, and the gate in validation.yml. Triggers on "new predictor", "ADMET endpoint", "add a model", "uncertainty", "error bar", "applicability domain", "provenance", "citation", "DOI", "benchmark", "validation", "VALIDATION.md", "is this validated".
---

# Validating a predictor

This repository's central claim is that **a predicted number is not a
measurement**, and that the difference is visible in the payload rather than
in a disclaimer. A predictor that ships without it does more damage than one
that does not ship — a bare point estimate reads like data, gets copied into a
slide, and stops being labelled somewhere between the two.

This is the most valuable rule in the repository and the one least visible from
the code, so it is written down here. All of it is enforced; where something is
convention rather than gate, this file says so.

## When to use this skill

- Adding a tool that estimates, scores, ranks or predicts anything.
- Changing a coefficient, a threshold or an engine version in an existing one.
- Adding or changing a reference dataset under `tests/validation/reference/`.
- Auditing a number that looks too good, or answering "is this validated?"

## When NOT to use this skill

- Adding a **deterministic** tool — a descriptor, a fingerprint, a substructure
  match, a scaffold. Those compute a definition, not an estimate, and wrapping
  one in a prediction envelope suggests an error bar where there is nothing to
  be wrong about. You still have to classify it (§2).
- Pure refactors that do not touch the numerical path.

## 1. The envelope

Every predictor returns a `Prediction` from
`services/chemistry/provenance.py` — stdlib dataclasses, not pydantic. Four
things, and none of them is optional:

```python
Prediction(
    value=...,                       # float | str | bool | None
    uncertainty=Uncertainty(...),    # never a lone number
    applicability=ApplicabilityDomain(...),
    provenance=Provenance(...),
    unit=..., caveat=..., extra={},
)
```

Note the asymmetry that catches people: the dataclass field is `applicability`,
but `as_dict()` emits the key **`applicability_domain`**. The payload keys
`tests/test_prediction_contract.py` requires are
`("value", "uncertainty", "applicability_domain", "provenance")`.

**`Uncertainty`** — `basis` is mandatory and is one of:

| basis | when |
|---|---|
| `MEASURED_BENCHMARK` | measured by `tests/validation/` against a public benchmark. The strongest, because it is reproducible from this tree |
| `PUBLISHED_ERROR` | the error the source paper reports |
| `ENSEMBLE_SPREAD` | the spread of an ensemble — e.g. docking pose scores |
| `STATED_ESTIMATE` | an honest guess, labelled as one |
| `NOT_APPLICABLE` | the value is exact (`Uncertainty.exact()`) |

`source` is required whenever `sigma` is set: *an error bar with no stated
origin is decoration.* Use `Uncertainty.from_sigma(...)` rather than computing
an interval by hand.

**`ApplicabilityDomain`** — `verdict` is `IN`, `BORDERLINE`, `OUT` or
`UNKNOWN`, with the individual `checks` visible, not just the verdict.
`from_checks()` does the standard mapping (0 failed → `IN`, 1 → `BORDERLINE`,
≥2 → `OUT`). If the model does not define a domain, say `UNKNOWN` via
`not_defined(why)` — do not guess one. When the verdict is `OUT` and no caveat
was given, `as_dict()` synthesises one; do not suppress it.

**`Provenance`** — `model`, `kind`, `version`, `trained_on`, `citations`.
`kind` is a `ModelKind`, and picking it is a claim: `PUBLISHED_QSPR`,
`PUBLISHED_RULE`, `SUBSTRUCTURE_ALERT`, `PHYSICS_ENGINE`,
`PUBLISHED_HEURISTIC`, `HEURISTIC`, `DETERMINISTIC_DESCRIPTOR`. The UI renders
`HEURISTIC` with a distinct amber rule precisely so an in-house correlation
cannot be read as a benchmarked model.

**Citations must resolve.** Add a module-level `Citation` constant beside the
sixteen already in `provenance.py`, with both `doi=` and `url=`.
`scripts/check_dois.py` regex-scans every git-tracked `.md .py .csv .toml .yml
.yaml .ts .tsx` and verifies each DOI **against the Crossref API** — registered,
not merely reachable, because publishers answer a non-browser client with 403.
It runs in `.github/workflows/docs-links.yml`. There is no way to add a citation
that escapes it except by not committing it.

## 2. Classify it, or the build fails

`tests/validation/test_inventory_is_complete.py` compares the live tool registry
against two hand-maintained sets and fails on anything unclassified:

- `_DETERMINISTIC_TOOLS` — *"Adding a name here is a claim that the tool is
  DETERMINISTIC, not a way to opt a predictor out of being listed."*
- `_PREDICTIVE_TOOLS` — maps the tool name to a capability in
  `CAPABILITY_INVENTORY` (`tests/validation/report.py`).

Every capability in `CAPABILITY_INVENTORY` is either backed by a passing
benchmark or listed in the **Unvalidated** table with *what validating it would
take*. Both answers are fine. Silence is not — that is exactly how a capability
quietly stops being listed as unvalidated.

If the predictor returns the full envelope, add its capability to
`PREDICTORS_RETURNING_MODEL_KIND` too. `docs/VALIDATION.md` makes that claim in
prose, so it lives as data and `tests/test_prediction_contract.py` checks it
against the live tools.

## 3. Benchmark it, or say you have not

A benchmark lives in `tests/validation/` and follows the two that are there.
Copy `test_esol_solubility.py`; it is the cleaner model.

1. **Reference data under `tests/validation/reference/`**, with the header the
   two existing files use: `WHAT THIS IS`, `SOURCE (primary)` with DOI,
   `SOURCE (redistribution)` with retrieval date and SHA-256, `RIGHTS`,
   `TRANSCRIPTION METHOD`, `WHAT IS *NOT* CLAIMED HERE`, `USED BY`. The section
   vocabulary is convention; three things about it are enforced —
   `read_reference_csv()` strips `#` lines so a header must use them, every DOI
   in it is Crossref-checked, and every URL in it is link-checked. *A validation
   number whose author might be us is not a validation number.*
2. **Gate constants at module level with the measured value in the comment**:
   ```python
   RMSE_CEILING = 1.15          # measured: 1.0994
   ```
3. **One test per claim**, then a final `test_record_result_for_the_validation_report`
   that builds a `ValidationResult` and calls `.record()`. There is no
   framework-level threshold evaluation: the test author computes `passed`
   and passes it in. `gates` is a dict of human-readable strings for display.
4. **Check the error bar against the measurement.** ESOL's suite asserts
   `ESOL_MEASURED_RMSE` (which feeds every solubility interval the app displays)
   is within 0.05 of what the run measured. An uncertainty that drifts from the
   error it claims to describe is worse than none.
5. **Regenerate the document**: `make validate`. Never hand-edit
   `docs/VALIDATION.md` — it is generated, and CI fails on a committed copy that
   disagrees with the run.

`.github/workflows/validation.yml` enforces three things beyond the tests: the
suite **cannot silently skip** (`GLOWSKY_REQUIRE_DOCKING=1`, plus a direct
assertion that the JUnit skip count is zero), `report.py --check` verifies the
document against the run, and failing benchmarks are printed explicitly.

`--check` is deliberately **not** a byte diff — Vina is multithreaded and not
bit-reproducible, so the RMSD moves between runs on identical code, and a gate
that cries wolf gets switched off. It enforces exactly four things: every
measured capability appears; every PASS/FAIL matches the run; a failed benchmark
is not presented as validated; and every inventory capability without a passing
result is listed as unvalidated.

## 4. A failing benchmark ships as failing

The re-docking benchmark measures 4.725 Å against a 2.0 Å criterion, and
`docs/VALIDATION.md` opens with a section saying so. **The criterion was not
moved to accommodate it.** `test_redocking_rmsd.py` carries a separate
regression ceiling of 5.5 Å with the comment that it *"is NOT a success
criterion and must never be mistaken for one"*, and `passed=` is bound to the
strict criterion even though a diagnostic metric clears.

If your benchmark fails, publish it and write down what fixing it would take.
That is a complete, acceptable outcome. Relaxing a gate to get green is not.

## Common mistakes

- **Returning a bare float.** The most common and the most damaging.
- **`sigma` with no `source`.** An error bar with no origin is decoration.
- **Inventing an applicability domain** because `UNKNOWN` looks weak. It is not
  weak; it is true.
- **Calling something `PUBLISHED_QSPR` when it is a two-term in-house
  correlation.** `HEURISTIC` exists and the UI marks it. hERG is currently a
  correlation on lipophilicity and a basic amine, and says so.
- **A DOI you recalled rather than looked up.** Crossref will reject it, but
  only after you have written prose around it.
- **Adding a tool and not classifying it.** The build tells you, with the two
  options spelled out in the failure message.
- **Editing `docs/VALIDATION.md` by hand.** Run `make validate`.
- **Presenting a docking score as an affinity.** It is a scoring-function value
  in kcal/mol; the repository says so in four places and validating an affinity
  claim would need measured Kd/Ki for a congeneric series.
- **Reproducing a model on the data it was fitted on and calling it
  generalisation.** The ESOL entry's "What this does not show" note exists
  because the Delaney compilation includes ESOL's own training compounds.

## Checklist

- [ ] Returns a `Prediction` with all four parts; `basis` and `verdict` chosen deliberately.
- [ ] `Citation` with a DOI that Crossref resolves (`make dois`).
- [ ] Classified in `_DETERMINISTIC_TOOLS` or `_PREDICTIVE_TOOLS`.
- [ ] Capability in `CAPABILITY_INVENTORY`, and in `PREDICTORS_RETURNING_MODEL_KIND` if it carries the envelope.
- [ ] Either a benchmark in `tests/validation/` or an Unvalidated row saying what one would take.
- [ ] Reference data carries the provenance header.
- [ ] `make validate` run and `docs/VALIDATION.md` committed as regenerated.
- [ ] `make lint && make cov` green.
- [ ] If it fails its criterion: published as failing, criterion unmoved.

## Reference

- `services/chemistry/provenance.py` — the envelope, the enums, the 16 citations.
- `services/chemistry/adapters/admet_rdkit.py` — `ESOL_MEASURED_RMSE`, `BACKEND_VERSION`.
- `tests/validation/_harness.py` — `ValidationResult`, `rmse`, `mae`, `r_squared`, `read_reference_csv`.
- `tests/validation/report.py` — `CAPABILITY_INVENTORY`, `PREDICTORS_RETURNING_MODEL_KIND`, `--check`.
- `tests/validation/test_esol_solubility.py` — the benchmark to copy.
- `tests/validation/test_redocking_rmsd.py` — how a failing benchmark is written.
- `tests/validation/test_inventory_is_complete.py` — the you-cannot-stay-silent gate.
- `tests/test_prediction_contract.py`, `tests/test_backends.py` — the payload gates.
- `scripts/check_dois.py`, `.github/workflows/docs-links.yml` — DOI verification.
- `docs/VALIDATION.md` — generated; read it before claiming anything is validated.
