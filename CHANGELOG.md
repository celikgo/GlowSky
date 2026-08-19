# Changelog

All notable changes to this project are documented here.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this
project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.1.0] - 2026-08-19

The first tagged release, and the first one with automated verification behind it.
Everything below the "Added" heading existed before this tag; what changed is that it
is now checked, and that the numbers it produces say how much they can be trusted.

### Added

**Continuous integration.** The repository previously had no GitHub Actions workflows
at all. It now has seven:

- `ci` — ruff, mypy, and pytest across Python 3.11/3.12/3.13 with coverage gated at 85%
  (91.23% at this tag), plus the desktop app's `tsc`, `vitest` and `eslint`. The matrix
  is what makes `requires-python = ">=3.11,<3.14"` a tested claim.
- `validation` — benchmarks against published reference values (below).
- `docker` — builds every image in every compose topology, runs `alembic upgrade head`
  *inside* the built image, and asserts the compose files refuse to resolve without a
  secret key.
- `migrations` — `alembic` up/down/up against Postgres 16, the engine production runs;
  the only place `downgrade()` is ever executed.
- `security` — the credential and RBAC regressions, `pip-audit`, `pnpm audit`, and a
  full-history `gitleaks` scan.
- `docs-links` — every URL resolves, and every cited DOI is verified against Crossref.
- `release` — this tag's own pipeline.

**Uncertainty, applicability domain and provenance on every prediction.**
`services/chemistry/provenance.py` defines the vocabulary and every predictor — the
seven ADMET endpoints, synthetic accessibility, and docking — returns a `Prediction`
carrying all three. A solubility prediction is reported as
`-1.99 logS, 95% CI [-4.15, +0.16]` where that interval comes from an error measured in
CI, not from a guess. 18 cited DOIs, each verified at its registration authority —
Crossref for the journal articles, wwPDB for the crystal structure — rather than by HTTP
status, on every push.

Two of the applicability domains are read out of the models' own internals rather than
asserted over them. SA score reports the fraction of a molecule's Morgan fragments that
are missing from `sascorer`'s PubChem table — each such fragment silently scores the
model's `-4` "unknown" default, so that fraction measures how much of the score is
evidence (aspirin 0%, cisplatin 30%, which is refused). Docking reports the spread
across the poses the run actually returned, labelled in the payload as the search
disagreeing with itself and explicitly **not** as the scoring function's error against
measured affinity — a quantity this repository has not measured and therefore does not
quote. A single returned pose reports no spread rather than a spread of zero.

**Validation against published reference values.** `tests/validation/`, gated in CI,
with results published to a generated `docs/VALIDATION.md`:

- ESOL solubility against 1128 measured values (Delaney 2004, via MoleculeNet):
  RMSE 1.0994 log units, MAE 0.8439, R² 0.7247, 68.1% within one log unit.
- Re-docking indinavir into PDB 1HSG from SMILES alone. **This benchmark currently
  fails its 2.0 Å criterion** — sampling recovers the crystal pose at 0.85 Å but the
  scoring function ranks a 4.73 Å pose first. It is published as failing rather than
  having the criterion moved.

`docs/VALIDATION.md` also lists every predictive capability with **no** benchmark
behind it, and what validating each would require. Six of the backend's seven ADMET
endpoints are on that list; only solubility has a benchmark behind it.

**Running a tagged release rather than the working tree.**
`docker-compose.release.yml` runs the published GHCR image; every other compose stack
builds from whatever is checked out, which is a moving target and not something a bug
report can identify. It carries no `build:` section anywhere, and the docker workflow
fails the build if one appears or if the three application services ever pin different
tags — a partial bump would otherwise run an API and a worker from different releases
against one database. Its default tag is a fifth version declaration, kept in step with
the other four by `tests/test_version_consistency.py`.

**Project hygiene.** `SECURITY.md` (with the known limitations documented as known),
`CONTRIBUTING.md`, `CODE_OF_CONDUCT.md`, this changelog, and a version-consistency test
covering the four places the version is declared.

### Fixed

- **Receptor preparation was missing hydrogens.** The `obabel` command documented in
  both the README and `docker-compose.docking.yml` omitted `-p 7.4`. Deposited PDB
  coordinates carry no hydrogens and Vina assigns hydrogen-bond atom types from the
  protonation state, so this measurably degraded docking. Found by the re-docking
  benchmark.
- **Three high-severity advisories** against `fast-uri` < 3.1.5, reaching the desktop
  app via `ketcher-react > ajv`. Found by `pnpm audit` on the security workflow's first
  run.
- **`ValidationResult.canonical_smiles` is `Optional`**, and 13 call sites that had
  already checked `valid` were passing `str | None` into functions requiring `str` —
  the mechanism by which a `None` reaches RDKit dressed as a molecule. Added `.smiles`
  and `.key` accessors that enforce the invariant.
- **A stray assignment mid-import-block** in `apps/api/main.py` made the 29 imports
  after it `E402`s.
- **`ToolRegistry.list()`** was annotated `-> list[ToolSpec]`, where `list` in that
  class body is the method being defined. Deferred by PEP 563, so it never raised — it
  simply never meant what it read as.
- **`retrosynthesis.suggest()`** built `best` from a conditional then re-derived the
  same condition to index it, leaving the `None` branch reachable on paper.
- **`ADMETBackend` / `DockingBackend`** declared `name` as a settable instance
  attribute, which no backend deriving its name from configuration can satisfy.
- **`pnpm-workspace.yaml`** carried pnpm's placeholder text (`esbuild: set this to true
  or false`) as a boolean, which would have ended every non-interactive CI install on
  `ERR_PNPM_IGNORED_BUILDS`.
- **A full pose range was rendered as a "100% CI"** in the desktop's prediction card —
  claiming total certainty about precisely the number whose purpose is to show that the
  docking search disagreed with itself. It now renders as a range.
- **A 3.12-only f-string** (backslash in an expression) that would have been a hard
  `SyntaxError` on the 3.11 matrix leg. Caught by ruff's `target-version = "py311"`.

### Changed — corrections to claims the code did not support

- The README said auth was gated by `GLOWSKY_AUTH_ENABLED`, "default off → single-tenant
  dev mode". That setting **does not exist**; auth is mandatory with no bypass. The
  comment understated the security posture.
- The README's docking example said "dock indinavir" while showing a 24-heavy-atom
  **fragment** of it, and described the output as "real affinities". A Vina score is
  not a binding affinity.
- The README said "there is no CI, so 3.11/3.12 are supported by declaration but never
  exercised". True when written; now they are exercised on every pull request.
- The ESOL uncertainty constant claimed 0.90 log units. The measured value is 1.0994,
  and a test now fails if the displayed error bar and the measured error drift apart.
- The re-docking reference SMILES had two of five stereocentres inverted — a different
  diastereomer. It is now derived from the deposited coordinates rather than written
  from memory.

### Known limitations

See `SECURITY.md` for the security ones and `docs/VALIDATION.md` for the scientific
ones. In brief: there is no key rotation, encryption at rest is one process-wide Fernet
key, tool arguments are not validated server-side, `egress: allowlist` on a container
tool silently means no network, and most predictive endpoints are unvalidated.

Desktop bundles are **unsigned**.

<!-- These point at pages that exist today. Once v0.1.0 is tagged they become
     .../compare/v0.1.0...HEAD and .../releases/tag/v0.1.0 respectively — the
     docs-links workflow checks every URL in this file on every push, so a link to a
     release that has not been cut yet is a build failure, not a placeholder. -->

[Unreleased]: https://github.com/celikgo/GlowSky/commits/main
[0.1.0]: https://github.com/celikgo/GlowSky/releases
