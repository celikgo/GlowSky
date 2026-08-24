# Contributing to Glowsky

Thanks for looking. This document is short on ceremony and long on the two or three
things about this codebase that are genuinely unusual, because those are what a
contributor actually needs to know.

## The rule that governs everything

> **LLMs reason and explain; deterministic chemistry computes.**

A molecule in Glowsky is a validated, canonicalized object — never a string a model
produced. Candidate structures are enumerated by RDKit reaction SMARTS and put through
the validation firewall; the model chooses *parameters*, not *atoms*.

There is a second half to that rule, and it is the one that is easier to break by
accident:

> **A number must carry its uncertainty, its applicability domain, and its provenance.**

A predicted ADMET property or docking score shown as a bare point estimate reads like a
measurement, and it is not one. Every predictor returns a
[`Prediction`](services/chemistry/provenance.py) with all three, and
`tests/test_backends.py` fails a new endpoint that omits any of them. If you are adding
anything that predicts a quantity, read that module first — it explains the vocabulary
and, more importantly, why it exists.

## Getting set up

```bash
make venv && make install     # Python 3.11-3.13; RDKit has no 3.14 wheels
make test                     # the suite
make lint                     # ruff + mypy, exactly what CI runs
```

`make venv` hardcodes the Apple-Silicon Homebrew interpreter. On anything else, create
the environment yourself — the directory name matters, the interpreter name does not:

```bash
python3 -m venv .venv313 && make install
```

Desktop app:

```bash
cd apps/desktop && pnpm install    # pnpm, not npm — there is no package-lock.json
pnpm typecheck && pnpm test && pnpm lint
```

## Before you open a pull request

Run what CI runs. It is all in the Makefile, and the workflows call the same commands,
so a green `make` locally means a green CI:

```bash
make lint          # ruff + mypy
make cov           # pytest with the 85% coverage gate
make validate      # the benchmark suite; regenerates docs/VALIDATION.md
```

Six workflows gate a pull request:

| workflow | what it will not let you merge |
|---|---|
| `ci` | lint or type errors; a test failure on Python 3.11, 3.12 or 3.13; coverage under 85%; a frontend type error, test failure or eslint error; a raw colour literal, a missing theme token or a contrast regression in the desktop app |
| `docker` | a Dockerfile that does not build, a compose topology that does not resolve, or an image that cannot run its own migrations |
| `migrations` | a migration that fails on Postgres, or a `downgrade()` that does not undo its `upgrade()` |
| `security` | a known-vulnerable dependency, a committed secret, or a regression in the credential and RBAC gates |
| `validation` | a predictor that has drifted away from published reference values, or a `docs/VALIDATION.md` that disagrees with the run |
| `docs-links` | a dead URL, or a DOI that is not registered |

## The parts that will surprise you

**Lint rules are stated, not inherited.** `[tool.ruff.lint]` in `pyproject.toml` pins
the rule set and the dev extra pins the version, so a lint failure always means the code
changed and never that the tool did. Every `# noqa` in this repository states *why* that
specific case is exempt. Please keep that up — a bare `# noqa` will be asked about.

**Broad `except Exception` needs a reason.** `BLE001` is on. There are thirteen
deliberate broad catches and each carries a comment explaining why that catch cannot be
narrower. Add the fourteenth if you need it; just say why.

**`docs/VALIDATION.md` is generated.** Do not edit it. Run `make validate`. CI
regenerates it and fails if your committed copy differs from what the suite measured —
a hand-maintained validation page becomes a specific false claim about accuracy.

**A new predictive tool must be classified.** `tests/validation/test_inventory_is_complete.py`
checks the tool registry against the capability inventory, so a new tool fails until you
either validate it against a benchmark or list it as unvalidated with what validating it
would require. Both answers are fine. Silence is not — that is exactly how a capability
quietly stops being listed as unvalidated.

**Reference data carries provenance.** Files in `tests/validation/reference/` have
headers naming the primary source, how the values were obtained, the rights position,
and what is *not* claimed. If you add one, match that standard. A validation number
whose author might be us is not a validation number.

**A structure is drawn on a light ground in every theme, and that is not a bug.**
Element colours are chemical identity, so a theme must never re-tint them — and no
published element palette is legible on both a light and a dark ground (the numbers are
in `apps/desktop/src/theme/cpk.ts`). So the drawing surface is what stays fixed and the
app around it themes. `.claude/skills/rendering-molecules` has the rest.

**Python 3.11 is the floor and it is load-bearing.** `ruff`'s `target-version = "py311"`
catches 3.12-only syntax — a backslash inside an f-string expression, for one — that
would otherwise be a hard `SyntaxError` on the oldest matrix leg.

## Commits and pull requests

Conventional-commit prefixes (`feat:`, `fix:`, `docs:`, `ci:`, `test:`, `refactor:`).
Say what changed and **why**; this codebase's comments carry a lot of reasoning and the
history is expected to do the same.

Branch off `main`, keep pull requests focused, and describe what you verified rather than
asserting it works.

## What is most useful right now

- **Validating an unvalidated capability.** [`docs/VALIDATION.md`](docs/VALIDATION.md)
  lists every predictor with no benchmark behind it and says what validating each would
  require. Seven of the eight ADMET endpoints are on that list. Turning any one of them
  into a real benchmark against public data is the highest-value contribution to this
  repository, and it is a self-contained piece of work.
- **A second re-docking case.** The docking benchmark currently has one structure, and
  one structure bounds nothing about average performance.
- **Server-side tool-argument validation** — `ToolSpec.input_schema` is advertised to the
  model but never enforced. See `docs/07-security-privacy.md` §5.

## Security

Do not open a public issue for a security problem. See [SECURITY.md](SECURITY.md).

## Licence

Apache 2.0. By contributing you agree your contributions are licensed under it.
