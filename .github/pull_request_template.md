<!--
Glowsky's rule is that a claim must be checkable. That applies to pull requests too: if
this change adds or alters a number the software reports, say what makes the new number
right, and say what it is not.

Delete any section that genuinely does not apply. Do not delete a section because the
answer is inconvenient — "unvalidated" and "I don't know" are acceptable answers here
and are exactly what docs/VALIDATION.md exists to record.
-->

## What this changes, and why

## How it was verified

<!-- The commands you ran and what they said, not "tests pass". If a benchmark moved,
     give the before and after. -->

## If this touches a predictor

- [ ] It returns a `Prediction` — uncertainty, applicability domain, provenance
- [ ] The applicability domain **bites**: there is a test showing an out-of-domain
      molecule being refused, not merely a domain field being present
- [ ] The uncertainty's `basis` is honest about where the band came from — a measured
      benchmark error and a stated judgement are different claims
- [ ] `docs/VALIDATION.md` is regenerated, and the capability is listed as validated
      **or** as unvalidated with what validating it would require
- [ ] The source header says what the number is NOT

## If this touches credentials, auth, or the agent loop

- [ ] There is a regression test, and it is gated in `.github/workflows/security.yml`
- [ ] No secret is logged, echoed in an error, or returned in a payload

## Anything a reviewer should push back on

<!-- Shortcuts taken, a criterion you were tempted to move, a number you could not
     verify. Saying so here is cheaper than it being found later. -->
