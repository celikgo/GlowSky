"""Run export: notebook/markdown builders + the export API endpoints."""
from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from apps.api.main import app
from services.reporting import build_markdown, build_notebook, notebook_json
from tests.conftest import tenant

_RUN = {
    "id": "run-123",
    "goal_text": "make 5 analogs, MW<300, no PAINS",
    "created_at": "2026-06-14T00:00:00+00:00",
    "plan": {"max_analogs": 5, "constraints": {"mw_max": 300, "exclude_pains": True},
             "rationale": "diversify the ring"},
    "trace": [{"step": 1, "tool": "validate_molecule", "tool_version": "0.1.0",
               "summary": "valid", "duration_ms": 1.2, "cache_hit": False}],
    "models_used": {"reasoning": "mock/mock"},
    "explanation": "Three analogs improved QED while staying drug-like.",
}
_MOLS = [
    {"name": "parent", "canonical_smiles": "c1ccccc1C(=O)O", "inchikey": "AAA",
     "properties": {}, "source": "user"},
    {"name": None, "canonical_smiles": "Cc1ccccc1C(=O)O", "inchikey": "BBB",
     "properties": {"mw": 136.15, "logp": 1.9, "tpsa": 37.3, "qed": 0.62,
                    "lipinski_pass": True, "has_pains": False}, "source": "generated"},
]


# --- builders -----------------------------------------------------------------


def test_notebook_is_valid_ipynb_and_reproducible():
    nb = build_notebook(_RUN, _MOLS)
    assert nb["nbformat"] == 4
    assert nb["metadata"]["glowsky"]["run_id"] == "run-123"
    # Round-trips as JSON (the on-disk .ipynb format).
    parsed = json.loads(notebook_json(_RUN, _MOLS))
    assert parsed["cells"]

    flat = "".join("".join(c["source"]) for c in nb["cells"])
    assert "from rdkit import Chem" in flat          # reproducible RDKit code
    assert "c1ccccc1C(=O)O" in flat                  # parent embedded
    assert "Cc1ccccc1C(=O)O" in flat                 # candidate embedded
    assert "Descriptors.MolWt" in flat               # recomputes, not just echoes


def test_notebook_code_cells_actually_execute():
    """The exported notebook must *run*: execute its code cells like a kernel would."""
    nb = build_notebook(_RUN, _MOLS)
    ns: dict = {}
    n_code = 0
    for cell in nb["cells"]:
        if cell["cell_type"] == "code":
            n_code += 1
            exec(compile("".join(cell["source"]), f"<cell {n_code}>", "exec"), ns)
    assert n_code >= 4
    assert len(ns["df"]) == 1            # one generated candidate, descriptors recomputed
    assert "passes" in ns["df"].columns  # constraints re-applied locally
    assert ns["df"].iloc[0]["mw"] > 0


def test_notebook_handles_a_run_with_no_candidates():
    nb = build_notebook({**_RUN, "trace": [], "explanation": None},
                        [{"name": "parent", "canonical_smiles": "CCO", "inchikey": "X",
                          "properties": {}, "source": "user"}])
    assert nb["cells"]  # still produces setup + parent cells, no crash


def test_markdown_report_contains_key_sections():
    md = build_markdown(_RUN, _MOLS)
    assert "make 5 analogs" in md
    assert "## Candidates" in md and "Cc1ccccc1C(=O)O" in md
    assert "## Execution trace" in md
    assert "Three analogs improved QED" in md  # the explanation
    assert "`run-123`" in md


# --- API ----------------------------------------------------------------------


def test_export_endpoints_produce_notebook_and_markdown():
    with TestClient(app) as client:
        run_id = client.post("/agent/design", json={
            "goal": "make 6 analogs, MW<320, no PAINS", "seed_smiles": "c1ccccc1C(=O)O",
        }).json()["run_id"]

        got = client.get(f"/runs/{run_id}")
        assert got.status_code == 200 and got.json()["run"]["id"] == run_id

        nb = client.get(f"/runs/{run_id}/export", params={"format": "ipynb"})
        assert nb.status_code == 200
        doc = json.loads(nb.text)  # must be valid notebook JSON
        assert doc["nbformat"] == 4
        assert "attachment" in nb.headers["content-disposition"]

        md = client.get(f"/runs/{run_id}/export", params={"format": "md"})
        assert md.status_code == 200 and "# Design report" in md.text

        bad = client.get(f"/runs/{run_id}/export", params={"format": "pdf"})
        assert bad.status_code == 422


@pytest.mark.real_auth
def test_run_export_is_tenant_isolated():
    with TestClient(app) as client:
        ha = tenant()["headers"]
        hb = tenant()["headers"]
        run_id = client.post("/agent/design", headers=ha,
                             json={"goal": "make 4 analogs", "seed_smiles": "c1ccccc1C(=O)O"},
                             ).json()["run_id"]
        # Org B cannot read or export org A's run.
        assert client.get(f"/runs/{run_id}", headers=hb).status_code == 404
        assert client.get(f"/runs/{run_id}/export", headers=hb).status_code == 404
