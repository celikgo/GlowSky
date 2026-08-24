# Glowsky — what this codebase will not let you do, and why

Read this before changing anything. Two rules govern everything here, both are
enforced by CI rather than by good intentions, and most of what looks like
friction in this repository is one of them.

## The two rules

**1. LLMs plan and explain; deterministic chemistry computes.**
`docs/05-technical-architecture.md:8` — *"Separation of probabilistic and
deterministic layers. LLMs plan/explain; a deterministic, validated Chemistry
Service computes. The agent reaches chemistry only through a typed tool
interface."* No LLM-emitted structure is persisted until RDKit canonicalises and
validates it. The model fills in argument values; the tool sequence is
hard-coded.

**2. A number carries its uncertainty, its applicability domain and its
provenance — always.** No predicted value is displayed as a bare point estimate,
ever, and not in a tooltip or behind a disclosure either: a number whose error
bar takes a click to see is a number that gets read without one. The provenance
carries a DOI that Crossref resolves, checked on every push.

Everything else follows from these. If a change makes either less true, it is
the wrong change even when it is a smaller diff.

## Stack (locked)

- **Backend** — Python 3.11–3.13, FastAPI, SQLAlchemy + Alembic, Celery for the
  slow path. RDKit is the chemistry. `services/` and `apps/api/`.
- **Desktop** — Tauri 2 shell around React 18 + Vite + TypeScript,
  `apps/desktop/`. **pnpm, not npm** — there is no `package-lock.json`. Eight
  screens on local component state, no router, so no deep links.
- **Structures** — RDKit-JS (WASM) for 2D, Ketcher for 2D editing, 3Dmol.js for
  3D. 3D coordinates are server-assisted via `POST /molecules/conformer`.
- **Docking** — AutoDock Vina + OpenBabel, container-gated.

Python 3.11 is the floor and it is load-bearing: ruff's `target-version =
"py311"` is what catches 3.12-only syntax that would be a hard `SyntaxError` on
the oldest matrix leg. mypy analyses at 3.12 for an unrelated numpy-stubs
reason, and is deliberately **not** strict.

## What Glowsky does NOT do

Stated as loudly as what it does, because this is the half a tool in this domain
usually gets wrong. The long version is README §"What Glowsky is not".

- **It does not measure anything.** A docking score is a scoring-function value
  in kcal/mol, not a binding affinity. A predicted hERG risk is a structural
  flag, not a cardiac safety finding. Passing a druglikeness battery predicts
  nothing — those rules describe where past drugs sat.
- **Most of it is not validated, and says so.** `docs/VALIDATION.md` is
  generated from a benchmark run and lists every capability with no benchmark
  behind it. Seven of the eight ADMET endpoints are on that list.
- **A failing benchmark ships as failing.** The 1HSG re-docking benchmark
  measures 4.725 Å against a 2.0 Å criterion and is published at the top of
  `docs/VALIDATION.md` as not meeting it. The criterion was not moved.
- **It is not a regulatory or safety assessment**, and nothing here substitutes
  for an assay.
- **A theme never changes a colour that encodes chemical meaning.** Oxygen is
  red in every theme, including the one you just added.

## Traps

- **`docs/VALIDATION.md` is generated. Do not edit it.** Run `make validate`. CI
  regenerates and fails if the committed copy disagrees with what the suite
  measured — a hand-maintained validation page becomes a specific false claim
  about accuracy, published under the project's name.
- **A new predictive tool must be classified or the build fails.**
  `tests/validation/test_inventory_is_complete.py` checks the tool registry
  against the capability inventory. Validate it against a benchmark, or list it
  as unvalidated with what validating it would require. Both are fine; silence
  is not.
- **Never write a SMILES from memory** into code, a fixture or a comment. A
  plausible-looking SMILES that is the wrong molecule is invisible in review and
  is the worst defect this codebase can ship.
- **Never recall a DOI.** `scripts/check_dois.py` verifies every one against
  Crossref, and it will catch you after you have written prose around it.
- **A raw colour under `apps/desktop/src` fails CI** — including the `0x1e2732`
  form, which already shipped once as a hand-copied duplicate of a token.
- **`# noqa` states why.** `BLE001` is on; there are thirteen deliberate broad
  catches and each says why it cannot be narrower. A bare `# noqa` gets asked
  about.
- **Lint rules are stated, not inherited.** `pyproject.toml` pins the rules and
  the dev extra pins the versions, so a lint failure always means the code
  changed and never that the tool did. Keep it that way.

## Skills available here

- `updating-design-tokens` — the desktop palette: the token contract, semantic
  naming, define-in-every-theme, contrast verification, the element exemption.
- `rendering-molecules` — why element colours are data and not theme, the
  depiction conventions, and what must never be inferred about a structure.
- `validating-a-predictor` — how a predictor earns its way in: the envelope, the
  capability inventory, the benchmark harness, the gate in `validation.yml`.

## Working agreement

- **Run what CI runs before pushing.** `make lint`, `make cov`, `make tokens`,
  `make validate`. The workflows call the same commands.
- **Do not weaken a gate to get green.** Not a coverage threshold, not a
  benchmark criterion, not a contrast floor. Fix the thing, or publish the
  failure and say what fixing it would take.
- **Do not add a rule to a skill or to this file that CI does not enforce.** An
  unenforced rule is a claim, and claims here are checkable.
- **Comments carry the reasoning.** This codebase explains *why this flag, why
  this ordering, why not the obvious alternative*, often with a measured number.
  Commits do the same. Conventional prefixes, one concern each, and say what you
  verified rather than asserting it works.
- **If something is scaffolded, the docs say scaffolded** — with a specific,
  falsifiable negative ("no `services/rag/`"), never a vague "not implemented".

## Where the detail lives

`README.md` · `CONTRIBUTING.md` · `docs/05-technical-architecture.md` (layers
and flows) · `docs/13-chemistry-tools-architecture.md` (the tool contract) ·
`docs/14-design-system.md` (the desktop palette, measured) ·
`docs/VALIDATION.md` (generated — what is and is not checked against the world).
