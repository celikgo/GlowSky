"""Validation against published reference values.

The distinction this package exists to enforce: the rest of tests/ checks that the
code does what THIS repository intends. These tests check that it agrees with
somebody else's published numbers. A unit test can pass on a wrong model, forever.

Every test here is gated in CI. Every reference value carries a provenance header
naming its source, its retrieval method, and what is and is not claimed about it.
The results are published to docs/VALIDATION.md, which is GENERATED from a run
rather than written — a validation document maintained by hand drifts from the code
it describes, and then it is worse than nothing.

A capability with no benchmark behind it is listed as UNVALIDATED in that document
rather than printed beside the ones that have been checked.
"""
