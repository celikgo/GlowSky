"""Validation: re-docking a crystallographic ligand back into its own binding site.

WHAT IS BEING VALIDATED
    That Glowsky's docking path — SMILES -> 3D embed -> PDBQT -> AutoDock Vina ->
    parsed pose -> geometry returned to the caller — recovers an experimentally
    observed binding mode. The ligand's crystal coordinates are thrown away; only its
    SMILES goes in. Success is the top-scored pose landing within 2.0 A heavy-atom
    RMSD of where crystallography actually found it.

WHY THIS IS THE STRONGEST TEST IN THE REPOSITORY
    Every other test here compares Glowsky against a number somebody computed. This
    one compares it against something somebody MEASURED, with X-rays, and deposited
    publicly. The reference answer is not an opinion about chemistry — it is where the
    atoms were.

    It also exercises the entire pipeline end to end. Ligand preparation, the PDBQT
    conversion, the command construction, Vina itself, the pose parser, and the
    multi-model .pdbqt splitter all have to be right simultaneously, because getting
    any one of them wrong moves the atoms.

WHAT THIS IS NOT
    - It is not evidence that Glowsky can predict where a NOVEL ligand binds. Re-docking
      into the ligand's own co-crystal structure is the easiest case in structure-based
      modelling: the protein is already in the conformation this ligand induced. Cross-
      docking and prospective docking are much harder and are not tested here.
    - It says nothing about binding AFFINITY. A pose can be geometrically right and its
      score still be a poor estimate of free energy. See services/chemistry/adapters/
      docking.py: a Vina score is not a binding affinity and must never be reported as
      one.
    - One structure is one structure. A single-case benchmark bounds nothing about
      average performance; it detects breakage in a pipeline that is otherwise only
      checked by mocks. Stated as such in docs/VALIDATION.md.
"""
from __future__ import annotations

import os
import pathlib
import shutil
import subprocess

import pytest
from rdkit import Chem, RDLogger
from rdkit.Chem import AllChem, rdMolAlign

from services.chemistry.adapters.docking import Pocket
from services.chemistry.adapters.vina import VinaDockingBackend
from tests.validation._harness import ROOT, ValidationResult, environment, read_reference_csv

RDLogger.DisableLog("rdApp.*")

DOCKING_EXAMPLES = ROOT / "examples" / "docking"

#: Set in CI (.github/workflows/validation.yml). When it is set, a skip becomes a
#: failure: a validation suite that silently skips its headline benchmark is exactly
#: as informative as not having one, and far more misleading.
REQUIRE_DOCKING = os.environ.get("GLOWSKY_REQUIRE_DOCKING") == "1"

_SOURCE = (
    "RCSB PDB 1HSG — Chen, Z. et al., J. Biol. Chem. 269, 26344 (1994); "
    "success criterion from Trott & Olson, J. Comput. Chem. 31, 455-461 (2010)"
)
_SOURCE_URL = "https://doi.org/10.2210/pdb1hsg/pdb"


def _tools_present() -> tuple[bool, str]:
    missing = [b for b in ("vina", "obabel") if shutil.which(b) is None]
    return (not missing), ", ".join(missing)


def _require_tools() -> None:
    ok, missing = _tools_present()
    if ok:
        return
    message = (
        f"re-docking validation needs {missing} on PATH. Install AutoDock Vina and "
        f"OpenBabel, or run the docking image (infra/docker/docking.Dockerfile)."
    )
    if REQUIRE_DOCKING:
        pytest.fail(f"GLOWSKY_REQUIRE_DOCKING=1 but {message}")
    pytest.skip(message)


@pytest.fixture(scope="module")
def case() -> dict:
    rows = read_reference_csv("redocking_crystal_poses.csv")
    assert len(rows) == 1, "expected exactly one re-docking case"
    return rows[0]


@pytest.fixture(scope="module")
def crystal_pose(case) -> Chem.Mol:
    """The experimental answer: crystal coordinates with real bond orders applied.

    AssignBondOrdersFromTemplate is doing double duty. It gives the crystal ligand the
    bond orders a PDB file does not carry, AND it verifies the reference SMILES is
    genuinely this ligand: it raises unless the two are the same heavy-atom graph.
    """
    ligand_pdb = DOCKING_EXAMPLES / f"{case['pdb_id'].lower()}_ligand.pdb"
    assert ligand_pdb.exists(), f"missing crystal ligand: {ligand_pdb}"

    raw = Chem.MolFromPDBFile(str(ligand_pdb), removeHs=True, sanitize=True)
    assert raw is not None, f"RDKit could not read {ligand_pdb}"

    template = Chem.MolFromSmiles(case["ligand_smiles"])
    assert template is not None, "reference ligand_smiles does not parse"
    return AllChem.AssignBondOrdersFromTemplate(template, raw)


def test_the_reference_smiles_is_the_deposited_ligand(case, crystal_pose):
    """Guard the benchmark's own premise before measuring anything against it.

    If the reference SMILES were not this ligand, every RMSD below would be measured
    between two different molecules and would mean nothing.
    """
    template = Chem.MolFromSmiles(case["ligand_smiles"])
    assert crystal_pose.GetNumHeavyAtoms() == template.GetNumHeavyAtoms() == 45
    assert crystal_pose.GetNumConformers() == 1
    assert Chem.MolToSmiles(Chem.RemoveHs(crystal_pose)) == Chem.MolToSmiles(template)


def test_rmsd_is_measured_in_place_not_after_superposition(crystal_pose):
    """The methodological guard that keeps this benchmark honest.

    A re-docking RMSD must be computed where the atoms are. RDKit offers both
    CalcRMS (in place) and GetBestRMS (superpose, then measure); using the latter
    would report ~0 A for a pose translated bodily out of the binding site and make
    the whole benchmark vacuous. This asserts the two behave differently and that the
    one used below is the in-place one.
    """
    import copy

    from rdkit.Geometry import Point3D

    moved = copy.deepcopy(crystal_pose)
    conf = moved.GetConformer()
    for i in range(moved.GetNumAtoms()):
        p = conf.GetAtomPosition(i)
        conf.SetAtomPosition(i, Point3D(p.x + 10.0, p.y, p.z))

    in_place = rdMolAlign.CalcRMS(moved, crystal_pose)
    superposed = rdMolAlign.GetBestRMS(moved, crystal_pose)

    assert in_place == pytest.approx(10.0, abs=1e-6), (
        "CalcRMS must measure in place: a 10 A rigid translation is a 10 A RMSD"
    )
    assert superposed < 0.01, (
        "GetBestRMS superposes first — demonstrating why it must not be used here"
    )


@pytest.fixture(scope="module")
def prepared_receptor(tmp_path_factory, case) -> pathlib.Path:
    """Convert the deposited receptor to the rigid .pdbqt Vina consumes."""
    _require_tools()
    workdir = tmp_path_factory.mktemp("receptor")
    src = DOCKING_EXAMPLES / f"{case['pdb_id'].lower()}_receptor.pdb"
    assert src.exists(), f"missing receptor: {src}"
    out = workdir / f"{case['pdb_id'].lower()}_receptor.pdbqt"
    # -xr: rigid receptor (no torsions), which is what Vina expects for the protein.
    subprocess.run(
        ["obabel", str(src), "-O", str(out), "-xr"],
        check=True, capture_output=True, text=True, timeout=300,
    )
    assert out.exists() and out.stat().st_size > 0, "OpenBabel produced no receptor"
    return out


@pytest.fixture(scope="module")
def redocked(case, prepared_receptor) -> dict:
    """Dock the ligand from SMILES alone and return the parsed result."""
    _require_tools()
    backend = VinaDockingBackend(
        # exhaustiveness above the default: a re-docking benchmark should measure the
        # method, not the sampling budget. A fixed seed keeps the run reproducible.
        exhaustiveness=16,
        num_modes=9,
        seed=42,
        receptors_dir=str(prepared_receptor.parent),
    )
    pocket = Pocket(
        center=(float(case["center_x"]), float(case["center_y"]), float(case["center_z"])),
        size=(float(case["size_x"]), float(case["size_y"]), float(case["size_z"])),
    )
    return backend.dock(case["ligand_smiles"], str(prepared_receptor), pocket)


def test_redocking_recovers_the_crystallographic_pose(case, crystal_pose, redocked, tmp_path):
    """The headline gate: top-scored pose within 2.0 A of the experimental answer."""
    max_rmsd = float(case["max_rmsd_angstrom"])

    assert redocked["poses"], "Vina returned no poses"
    best_pdbqt = redocked["best_pose_pdbqt"]
    assert best_pdbqt, "the docking backend returned a score but no geometry"

    # PDBQT -> PDB -> RDKit, with the reference bond orders applied so the comparison
    # is between two representations of the same molecule.
    pose_pdbqt = tmp_path / "best_pose.pdbqt"
    pose_pdb = tmp_path / "best_pose.pdb"
    pose_pdbqt.write_text(best_pdbqt)
    subprocess.run(
        ["obabel", str(pose_pdbqt), "-O", str(pose_pdb)],
        check=True, capture_output=True, text=True, timeout=120,
    )
    raw_pose = Chem.MolFromPDBFile(str(pose_pdb), removeHs=True, sanitize=True)
    assert raw_pose is not None, "could not read back the docked pose"
    template = Chem.MolFromSmiles(case["ligand_smiles"])
    docked = AllChem.AssignBondOrdersFromTemplate(template, raw_pose)

    rmsd = rdMolAlign.CalcRMS(docked, crystal_pose)

    ValidationResult(
        capability="Docking — re-docking a crystallographic pose",
        model=f"AutoDock Vina via services/chemistry/adapters/vina.py ({redocked['engine']})",
        benchmark=f"{case['pdb_id']} self-docking, heavy-atom RMSD to the deposited pose",
        source=_SOURCE,
        source_url=_SOURCE_URL,
        n=1,
        metrics={
            "rmsd_angstrom": round(rmsd, 3),
            "top_score_kcal_per_mol": round(float(redocked["score"]), 2),
            "n_poses": len(redocked["poses"]),
        },
        gates={"rmsd_angstrom": f"<= {max_rmsd}"},
        passed=rmsd <= max_rmsd,
        notes=(
            "Self-docking: the receptor is already in the conformation this ligand induced, "
            "which is the easiest case in structure-based modelling. It is evidence that the "
            "SMILES -> embed -> PDBQT -> Vina -> pose-parse pipeline is correct end to end, "
            "NOT evidence that Glowsky can place a novel ligand. The score is reported for "
            "completeness and is not a binding affinity. One structure bounds nothing about "
            "average performance."
        ),
        environment={**environment(), "engine": str(redocked["engine"])},
    ).record()

    assert rmsd <= max_rmsd, (
        f"re-docked pose is {rmsd:.2f} A from the {case['pdb_id']} crystal pose, "
        f"above the {max_rmsd} A success criterion"
    )
