"""Shared machinery for the validation suite: metrics, and the results file.

Every validation test records its outcome here, and tests/validation/report.py turns
the accumulated record into docs/VALIDATION.md. That indirection is deliberate: the
published document is a report of a run, so it cannot claim a result the suite did
not actually produce.
"""
from __future__ import annotations

import json
import math
import os
import pathlib
from dataclasses import asdict, dataclass, field

ROOT = pathlib.Path(__file__).resolve().parents[2]
REFERENCE_DIR = pathlib.Path(__file__).resolve().parent / "reference"

#: Where each test deposits its result. Overridable so a local run does not clobber
#: whatever a CI run left behind.
RESULTS_PATH = pathlib.Path(
    os.environ.get("GLOWSKY_VALIDATION_RESULTS", ROOT / "validation-results.json")
)


@dataclass
class ValidationResult:
    """One benchmark's outcome, in the form docs/VALIDATION.md publishes."""

    capability: str          #: the Glowsky capability under test, e.g. "ADMET: aqueous solubility"
    model: str               #: the model being validated
    benchmark: str           #: the reference set
    source: str              #: citation for the reference values
    source_url: str
    n: int                   #: how many reference points were compared
    metrics: dict[str, float]
    gates: dict[str, str]    #: metric -> the threshold expression that had to hold
    passed: bool
    notes: str = ""
    #: Versions that make the numbers reproducible.
    environment: dict[str, str] = field(default_factory=dict)

    def record(self) -> None:
        """Append this result to the run's results file."""
        existing = []
        if RESULTS_PATH.exists():
            try:
                existing = json.loads(RESULTS_PATH.read_text())
            except json.JSONDecodeError:
                existing = []
        # Replace any earlier entry for the same capability so a re-run does not
        # accumulate stale duplicates in the generated document.
        existing = [e for e in existing if e.get("capability") != self.capability]
        existing.append(asdict(self))
        RESULTS_PATH.write_text(json.dumps(existing, indent=2, sort_keys=True) + "\n")


def rmse(errors: list[float]) -> float:
    return math.sqrt(sum(e * e for e in errors) / len(errors))


def mae(errors: list[float]) -> float:
    return sum(abs(e) for e in errors) / len(errors)


def r_squared(measured: list[float], predicted: list[float]) -> float:
    """Coefficient of determination against the measured mean.

    Note this is 1 - SS_res/SS_tot computed against the OBSERVED values, not the square
    of a correlation coefficient. For a model that was not fitted to this particular
    sample the two differ, and the version reported here is the stricter one: it
    penalises systematic bias, which a correlation coefficient does not see at all.
    """
    mean = sum(measured) / len(measured)
    ss_tot = sum((m - mean) ** 2 for m in measured)
    ss_res = sum((m - p) ** 2 for m, p in zip(measured, predicted, strict=True))
    return 1.0 - ss_res / ss_tot


def environment() -> dict[str, str]:
    """Versions a reader needs in order to reproduce a number."""
    import sys

    import rdkit

    return {
        "python": sys.version.split()[0],
        "rdkit": rdkit.__version__,
    }


def read_reference_csv(name: str) -> list[dict[str, str]]:
    """Read a reference CSV, skipping its '#' provenance header.

    The header is not decoration and is not stripped from the file: it travels with the
    data so that a copy of the file taken out of this repository still says where the
    numbers came from.
    """
    import csv

    path = REFERENCE_DIR / name
    lines = [ln for ln in path.read_text().splitlines() if not ln.startswith("#")]
    return list(csv.DictReader(lines))
