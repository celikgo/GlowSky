"""Real ADMET/docking backends: RDKit-QSPR estimates + Vina engine wiring.

The adapter backends are module-level singletons; every test that swaps one restores
the default so the 'not configured' contract other tests rely on is never leaked.
"""
from __future__ import annotations

import contextlib

import pytest

from services.chemistry.adapters import BackendNotConfigured, admet, docking
from services.chemistry.adapters.admet_rdkit import RDKitQSPRADMET
from services.chemistry.adapters.docking import Pocket
from services.chemistry.adapters.vina import VinaDockingBackend
from services.tools.catalog import build_default_registry
from services.tools.context import ExecutionContext
from services.tools.executor import ToolExecutionService

ASPIRIN = "CC(=O)Oc1ccccc1C(=O)O"


@contextlib.contextmanager
def admet_backend(backend):
    original = admet._backend
    admet.set_backend(backend)
    try:
        yield
    finally:
        admet.set_backend(original)


# --- RDKit-QSPR ADMET ---------------------------------------------------------


def test_rdkit_admet_returns_all_endpoints_with_provenance():
    out = RDKitQSPRADMET().predict(ASPIRIN, RDKitQSPRADMET.endpoints)
    assert set(out) == set(RDKitQSPRADMET.endpoints)
    for ep, pred in out.items():
        assert "value" in pred, ep
        assert "method" in pred and "confidence" in pred  # honest provenance on every value
        assert pred["applicability_domain"] in {"in", "borderline", "out"}


def test_esol_solubility_is_in_a_sane_range():
    # Aspirin's experimental logS ≈ -1.7..-2.1; ESOL should land in a believable window.
    sol = RDKitQSPRADMET().predict(ASPIRIN, ["solubility"])["solubility"]
    assert sol["method"].startswith("ESOL")
    assert -5.0 < sol["value"] < 1.0
    assert sol["mg_per_ml"] > 0


def test_bbb_rule_flags_a_large_polar_molecule_as_non_penetrant():
    # Glucose (TPSA ~110, very polar) should not be flagged BBB-penetrant.
    glucose = "OC[C@@H]1OC(O)[C@H](O)[C@@H](O)[C@@H]1O"
    bbb = RDKitQSPRADMET().predict(glucose, ["bbb"])["bbb"]
    assert bbb["value"] is False
    assert 0.0 <= bbb["probability"] <= 1.0


def test_unsupported_endpoint_is_reported_not_invented():
    out = RDKitQSPRADMET().predict(ASPIRIN, ["clearance"])
    assert "error" in out["clearance"]


def test_predict_admet_tool_uses_configured_backend():
    svc = ToolExecutionService(build_default_registry())
    with admet_backend(RDKitQSPRADMET()):
        res = svc.execute("predict_admet", {"canonical_smiles": ASPIRIN,
                                            "endpoints": ["solubility", "herg"]}, ExecutionContext())
    assert res.output["backend"] == "rdkit-qspr"
    assert "solubility" in res.output["predictions"]


def test_predict_admet_still_not_configured_by_default():
    # Default module backend must stay 'not configured' (never fabricate).
    svc = ToolExecutionService(build_default_registry())
    from services.tools.executor import ToolExecutionError
    with pytest.raises(ToolExecutionError) as ei:
        svc.execute("predict_admet", {"canonical_smiles": ASPIRIN}, ExecutionContext())
    assert isinstance(ei.value.__cause__, BackendNotConfigured)


# --- Vina docking backend -----------------------------------------------------


def test_vina_command_construction():
    be = VinaDockingBackend(vina_bin="vina", exhaustiveness=16, num_modes=5, seed=7)
    cmd = be.build_command("rec.pdbqt", "lig.pdbqt", "out.pdbqt",
                           Pocket(center=(1.0, 2.0, 3.0), size=(20.0, 20.0, 20.0)))
    assert cmd[0] == "vina"
    assert "--receptor" in cmd and "rec.pdbqt" in cmd
    assert cmd[cmd.index("--center_x") + 1] == "1.0"
    assert cmd[cmd.index("--exhaustiveness") + 1] == "16"
    assert cmd[cmd.index("--seed") + 1] == "7"


def test_vina_output_parsing_picks_the_best_pose():
    stdout = """
mode |   affinity | dist from best mode
     | (kcal/mol) | rmsd l.b.| rmsd u.b.
-----+------------+----------+----------
   1       -8.4       0.000      0.000
   2       -7.9       1.234      2.345
   3       -7.1       2.013      3.456
"""
    poses = VinaDockingBackend.parse_output(stdout)
    assert len(poses) == 3
    best = min(poses, key=lambda p: p["affinity"])
    assert best["mode"] == 1 and best["affinity"] == -8.4


def test_vina_split_pose_models_pairs_geometry_with_affinity():
    # A two-model Vina output .pdbqt (the per-pose blocks Vina writes to --out), trimmed
    # to a couple of atoms each — exercises the MODEL/REMARK/ENDMDL parsing.
    out_pdbqt = """MODEL 1
REMARK VINA RESULT:    -8.4      0.000      0.000
ROOT
ATOM      1  N   LIG d   1      11.224  25.382   3.001  1.00  0.00    -0.345 N
ATOM      2  C   LIG d   1      12.001  24.553   3.882  1.00  0.00    +0.123 C
ENDROOT
TORSDOF 3
ENDMDL
MODEL 2
REMARK VINA RESULT:    -7.1      1.984      3.221
ROOT
ATOM      1  N   LIG d   1      10.998  25.101   3.330  1.00  0.00    -0.345 N
ENDROOT
TORSDOF 3
ENDMDL
"""
    poses = VinaDockingBackend.split_pose_models(out_pdbqt)
    assert [p["mode"] for p in poses] == [1, 2]
    assert poses[0]["affinity"] == -8.4 and poses[1]["affinity"] == -7.1
    # The geometry block carries the real atom coordinates a viewer can render.
    assert "ATOM      1  N   LIG" in poses[0]["pdbqt"]
    assert poses[0]["pdbqt"].count("ATOM") == 2 and poses[1]["pdbqt"].count("ATOM") == 1


def test_vina_raises_not_configured_when_binary_missing():
    be = VinaDockingBackend(vina_bin="vina-does-not-exist", obabel_bin="obabel-nope")
    with pytest.raises(BackendNotConfigured):
        be.dock("c1ccccc1", "missing-receptor.pdbqt", Pocket((0, 0, 0), (10, 10, 10)))


def test_configure_backends_wires_vina_from_settings():
    # The docker-compose.docking.yml overlay sets GLOWSKY_DOCKING_BACKEND=vina; this is the
    # wiring that turns that env into a live VinaDockingBackend on the dock tool seam.
    from types import SimpleNamespace

    from services.chemistry.adapters import docking
    from services.chemistry.adapters.vina import VinaDockingBackend
    from services.chemistry.adapters.wiring import configure_backends

    settings = SimpleNamespace(
        admet_backend="none", docking_backend="vina", vina_bin="vina", obabel_bin="obabel"
    )
    original = docking._backend
    try:
        summary = configure_backends(settings)
        assert summary["docking"] == "autodock-vina (vina)"
        assert isinstance(docking._backend, VinaDockingBackend)
    finally:
        docking.set_backend(original)
