# Validation

<!-- GENERATED FILE — DO NOT EDIT BY HAND.
     Produced by `python -m tests.validation.report` from a run of the
     validation suite, and checked in CI (.github/workflows/validation.yml),
     which fails if this file disagrees with what the suite actually measured. -->

This page reports how Glowsky's predictive components compare against **published**
reference values — measurements and results whose author is somebody other than this
project. It is generated from a run of `tests/validation/`, so every number below was
produced by code in this repository at the commit that generated it.

**The second table is the important one.** Publishing the benchmarks you pass is easy.
The `Unvalidated` table lists every predictive capability with no benchmark behind it,
so a reader can tell which numbers have been checked against the world and which have
only been checked against this project's own intentions.

This file carries no generation timestamp on purpose. CI regenerates it and fails
if the result differs from what is committed, so its content must depend only on
the measurements — a clock in the file would make every run differ from every
other. Git already records when it changed.

---

## Not currently meeting its criterion

Stated here, at the top, rather than left to be discovered further down. These
benchmarks run and are measured; they do not meet the success criterion they are
judged against, and the criterion has not been moved to accommodate that.

- **Docking — re-docking a crystallographic pose** — best_pose_rmsd_angstrom = 0.853, n_poses = 8, rmsd_angstrom = 4.725, top_score_kcal_per_mol = -10.23. See below for what this means.


---

## Benchmark results

### ADMET — aqueous solubility (logS)

- **Status:** PASS — meets its stated criterion
- **Model under test:** ESOL (Delaney 2004 coefficients), as implemented in services/chemistry/adapters/admet_rdkit.py
- **Benchmark:** Delaney / ESOL compilation, 1128 measured aqueous solubilities (_n_ = 1128)
- **Reference source:** Delaney, J. S., J. Chem. Inf. Comput. Sci. 44(3), 1000-1005 (2004); retrieved via MoleculeNet (Wu et al., Chem. Sci. 9, 513-530, 2018)
  <https://doi.org/10.1021/ci034243x>

| metric | measured | gate |
|---|---|---|
| `fraction_within_1_log` | 0.6809 | `>= 0.65` |
| `mae_log_units` | 0.8439 | `<= 0.9` |
| `mean_signed_error` | 0.2782 | `\|x\| <= 0.35` |
| `r_squared` | 0.7247 | `>= 0.7` |
| `rmse_log_units` | 1.0994 | `<= 1.15` |

_Measured with: python 3.13.2, rdkit 2026.03.5._

> **What this does not show.** Reproduction of a published model on its own domain, NOT generalisation: the Delaney compilation includes the compounds ESOL was fitted on. An RMSE near one log unit is a factor of ten in concentration, which is why the predictor returns an interval rather than a point estimate. The measured RMSE here is the value used to build every solubility confidence interval Glowsky reports.

### Docking — re-docking a crystallographic pose

- **Status:** **FAIL — does not meet its stated criterion**
- **Model under test:** AutoDock Vina via services/chemistry/adapters/vina.py (AutoDock Vina v1.2.5)
- **Benchmark:** 1HSG self-docking, heavy-atom RMSD to the deposited pose (_n_ = 1)
- **Reference source:** RCSB PDB 1HSG — Chen, Z. et al., J. Biol. Chem. 269, 26344 (1994); success criterion from Trott & Olson, J. Comput. Chem. 31, 455-461 (2010)
  <https://doi.org/10.2210/pdb1hsg/pdb>

| metric | measured | gate |
|---|---|---|
| `best_pose_rmsd_angstrom` | 0.853 | `not gated (diagnostic)` |
| `n_poses` | 8 | — |
| `rmsd_angstrom` | 4.725 | `<= 2.0` |
| `top_score_kcal_per_mol` | -10.23 | — |

_Measured with: engine AutoDock Vina v1.2.5, python 3.13.15, rdkit 2026.03.5._

> **What this does not show.** Self-docking: the receptor is already in the conformation this ligand induced, which is the easiest case in structure-based modelling. It is evidence that the SMILES -> embed -> PDBQT -> Vina -> pose-parse pipeline is correct end to end, NOT evidence that Glowsky can place a novel ligand. The score is reported for completeness and is not a binding affinity. One structure bounds nothing about average performance.

---

## Unvalidated

These capabilities are shipped and are **not** validated against any published
reference. They are listed here rather than beside the validated ones because a
uniform panel of numbers is precisely how an in-house heuristic ends up being read
as a measurement. Each entry says what a real validation would require.

Every one of these returns its `ModelKind` in the API payload, so a caller can tell
programmatically which of these it is looking at without consulting this page.

| capability | what validating it would take |
|---|---|
| ADMET — CYP3A4 substrate likelihood | would need a measured CYP3A4 substrate/non-substrate set |
| ADMET — blood-brain barrier penetration | would need a measured CNS penetration set. The current rule models passive diffusion only and knows nothing about P-gp efflux |
| ADMET — hERG liability | would need measured hERG IC50 data. Currently a two-term correlation on lipophilicity and a basic amine |
| ADMET — logD7.4 | would need a measured logD set (e.g. a public lipophilicity benchmark). The current model has no ionization term at all, so it cannot be right for any acid or base |
| ADMET — metabolic stability | would need measured microsomal clearance, per species and matrix. The current output maps to no experimental unit |
| ADMET — plasma protein binding | would need measured fraction-bound data, and a model that can resolve the 99%-99.9% region where the decisions actually are |
| Docking — binding affinity from the Vina score | NOT VALIDATED AND NOT CLAIMED. A Vina score is not a binding affinity. Validating an affinity claim would need measured Kd/Ki for a congeneric series, and Glowsky does not present the score as an affinity anywhere |
| Docking — re-docking a crystallographic pose | MEASURED AND FAILING, not merely unmeasured. Re-docking into PDB 1HSG recovers the crystal pose during sampling (0.85 A) but the scoring function ranks a 4.73 A pose first, above the 2.0 A criterion — so the pose a user actually gets is the wrong binding mode. Improving it most likely means better receptor preparation (a dedicated tool rather than OpenBabel, and retaining the conserved flap water) rather than a different engine |
| MPO desirability score | not a predictive model — a weighted desirability function over descriptors. There is no ground truth to validate it against; it encodes a preference, and the preference is the thing being expressed |
| Med-chem rule battery (Lipinski, Veber, Ghose, Egan, Muegge, Ro3) | deterministic threshold rules reproducing published criteria. tests/test_medchem.py checks the thresholds against the published values; there is no accuracy to measure because the rules ARE the definition |
| Retrosynthesis — template disconnections | would need a reaction-route benchmark with expert-validated routes. The current implementation is a small hand-written template set and finds only one-step disconnections it already knows |
| Structural alerts (PAINS, BRENK) | deterministic substructure matching against RDKit's published catalogues. Exact by construction; what a match MEANS is the uncertain part, and that is not something a benchmark can settle |
| Synthetic accessibility (SA score) | would need expert-assigned synthesizability rankings of the kind Ertl & Schuffenhauer used. Reproduces the published algorithm via RDKit Contrib; the algorithm is not re-derived here |

---

## What none of this is

Every number Glowsky produces is a **triage and prioritisation aid**: something to
help decide which compound to make next. Specifically, and regardless of how good a
benchmark result above looks:

- **A prediction is not a measurement.** The solubility model's own error bar is
  about one log unit — a factor of ten in concentration.
- **A docking score is not a binding affinity.** Vina's score is a scoring-function
  value. Recovering a crystal pose is evidence about *geometry*, and says nothing
  about the strength of binding.
- **None of this is a regulatory or safety assessment.** A predicted hERG risk is a
  structural flag for follow-up, not a cardiac safety finding.
- **Out-of-domain values are not usable.** Where a molecule falls outside a model's
  applicability domain, the prediction carries a `caveat` field in the payload and
  is reported for transparency only.

## Reproducing this

```bash
make validate          # run the validation suite and regenerate this file
```

The re-docking benchmark needs AutoDock Vina and OpenBabel on `PATH`; without them
it skips locally. In CI it cannot skip — `.github/workflows/validation.yml` sets
`GLOWSKY_REQUIRE_DOCKING=1`, which turns a skip into a failure.

Reference values and their provenance live in `tests/validation/reference/`. Every
file there carries a header naming its source, how it was obtained, and what is and
is not claimed about it.
