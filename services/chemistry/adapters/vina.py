"""AutoDock Vina docking backend (real engine, subprocess-wrapped).

Wires the `dock` tool seam to a real AutoDock Vina / smina binary. Ligand prep is
done with RDKit (3D embed + MMFF) and converted to PDBQT via OpenBabel; the receptor
is supplied as a pre-prepared `.pdbqt`. If the required binaries aren't on PATH, the
backend raises BackendNotConfigured rather than inventing a score — consistent with
Glowsky's "never fabricate" rule. Enable with GLOWSKY_DOCKING_BACKEND=vina.

The non-IO parts — command construction and Vina-output parsing — are pure functions so
they're unit-tested without the binary present.
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile

from services.chemistry.adapters import BackendNotConfigured
from services.chemistry.adapters.docking import Pocket

# Vina prints a results table; each pose row starts with the mode index.
#    mode |   affinity | dist from best mode
#       1       -7.5       0.000      0.000
_POSE_ROW = re.compile(
    r"^\s*(\d+)\s+(-?\d+\.\d+)\s+(\d+\.\d+)\s+(\d+\.\d+)\s*$"
)

# Vina writes each docked pose as a MODEL block in the output .pdbqt, tagged with its
# affinity:  REMARK VINA RESULT:    -8.4      0.000      0.000
_VINA_RESULT = re.compile(r"^REMARK\s+VINA RESULT:\s+(-?\d+\.\d+)")


class VinaDockingBackend:
    """Dock a ligand into a receptor pocket via the AutoDock Vina binary."""

    def __init__(
        self,
        vina_bin: str = "vina",
        obabel_bin: str = "obabel",
        exhaustiveness: int = 8,
        num_modes: int = 9,
        seed: int = 42,
    ) -> None:
        self.vina_bin = vina_bin
        self.obabel_bin = obabel_bin
        self.exhaustiveness = exhaustiveness
        self.num_modes = num_modes
        self.seed = seed

    @property
    def name(self) -> str:
        return f"autodock-vina ({self.vina_bin})"

    # --- pure helpers (unit-tested without the binary) ------------------------

    def build_command(
        self, receptor: str, ligand: str, out: str, pocket: Pocket
    ) -> list[str]:
        cx, cy, cz = pocket.center
        sx, sy, sz = pocket.size
        return [
            self.vina_bin,
            "--receptor", receptor,
            "--ligand", ligand,
            "--out", out,
            "--center_x", str(cx), "--center_y", str(cy), "--center_z", str(cz),
            "--size_x", str(sx), "--size_y", str(sy), "--size_z", str(sz),
            "--exhaustiveness", str(self.exhaustiveness),
            "--num_modes", str(self.num_modes),
            "--seed", str(self.seed),
        ]

    @staticmethod
    def parse_output(stdout: str) -> list[dict]:
        """Parse Vina's pose table into [{mode, affinity, rmsd_lb, rmsd_ub}, ...]."""
        poses = []
        for line in stdout.splitlines():
            m = _POSE_ROW.match(line)
            if m:
                poses.append({
                    "mode": int(m.group(1)),
                    "affinity": float(m.group(2)),
                    "rmsd_lb": float(m.group(3)),
                    "rmsd_ub": float(m.group(4)),
                })
        return poses

    @staticmethod
    def split_pose_models(out_pdbqt: str) -> list[dict]:
        """Split Vina's multi-model output .pdbqt into per-pose blocks.

        Returns [{mode, affinity, pdbqt}, ...] in file order — the 3D coordinates a
        structure viewer renders, paired with each pose's docked affinity (read from
        its `REMARK VINA RESULT` line). A pose viewer needs the geometry, not just the
        scalar score, so we surface the real atoms instead of discarding them.
        """
        poses: list[dict] = []
        current: list[str] | None = None
        mode = 0
        affinity: float | None = None
        for line in out_pdbqt.splitlines():
            if line.startswith("MODEL"):
                current = []
                mode += 1
                affinity = None
            elif line.startswith("ENDMDL"):
                if current is not None:
                    poses.append({
                        "mode": mode,
                        "affinity": affinity,
                        "pdbqt": "\n".join(current) + "\n",
                    })
                current = None
            elif current is not None:
                m = _VINA_RESULT.match(line)
                if m:
                    affinity = float(m.group(1))
                current.append(line)
        return poses

    # --- real docking ---------------------------------------------------------

    def _require_tools(self) -> None:
        missing = [b for b in (self.vina_bin, self.obabel_bin) if shutil.which(b) is None]
        if missing:
            raise BackendNotConfigured(
                f"docking backend '{self.name}' needs these on PATH: {', '.join(missing)}. "
                "Install AutoDock Vina + OpenBabel, or register your engine as a container "
                "tool (docs/13 §6). Glowsky never fabricates docking results."
            )

    def _prepare_ligand_pdbqt(self, ligand_smiles: str, workdir: str) -> str:
        """SMILES -> 3D (RDKit ETKDG + MMFF) -> PDB -> PDBQT (OpenBabel)."""
        from rdkit import Chem
        from rdkit.Chem import AllChem

        mol = Chem.MolFromSmiles(ligand_smiles)
        if mol is None:
            raise ValueError(f"invalid ligand SMILES: {ligand_smiles!r}")
        mol = Chem.AddHs(mol)
        params = AllChem.ETKDGv3()
        params.randomSeed = self.seed
        if AllChem.EmbedMolecule(mol, params) != 0:
            raise ValueError(f"3D embedding failed for ligand: {ligand_smiles!r}")
        AllChem.MMFFOptimizeMolecule(mol)

        pdb_path = os.path.join(workdir, "ligand.pdb")
        pdbqt_path = os.path.join(workdir, "ligand.pdbqt")
        Chem.MolToPDBFile(mol, pdb_path)
        subprocess.run(
            [self.obabel_bin, pdb_path, "-O", pdbqt_path, "--partialcharge", "gasteiger"],
            check=True, capture_output=True, text=True,
        )
        return pdbqt_path

    def dock(self, ligand_smiles: str, receptor_ref: str, pocket: Pocket) -> dict:
        self._require_tools()
        if not os.path.exists(receptor_ref):
            raise BackendNotConfigured(
                f"receptor not found: {receptor_ref!r}. Provide a prepared receptor .pdbqt."
            )

        with tempfile.TemporaryDirectory(prefix="glowsky-vina-") as workdir:
            ligand_pdbqt = self._prepare_ligand_pdbqt(ligand_smiles, workdir)
            out_path = os.path.join(workdir, "out.pdbqt")
            cmd = self.build_command(receptor_ref, ligand_pdbqt, out_path, pocket)
            proc = subprocess.run(cmd, check=True, capture_output=True, text=True,
                                  timeout=self.resources_timeout_s)
            poses = self.parse_output(proc.stdout)
            if not poses:
                raise RuntimeError(f"Vina produced no poses; stdout:\n{proc.stdout[-500:]}")

            # Read back the docked geometry the temp dir is about to discard, and attach
            # each pose's 3D coordinates (.pdbqt block) to its scored row by mode index.
            with open(out_path) as fh:
                geom_by_mode = {g["mode"]: g["pdbqt"] for g in self.split_pose_models(fh.read())}
            for p in poses:
                p["pdbqt"] = geom_by_mode.get(p["mode"])

            best = min(poses, key=lambda p: p["affinity"])
            return {
                "score": best["affinity"],
                "score_unit": "kcal/mol",
                "num_modes": len(poses),
                "poses": poses,
                "best_pose_pdbqt": best.get("pdbqt"),
                "pocket": {"center": list(pocket.center), "size": list(pocket.size)},
            }

    # Vina runs can take minutes; align with the tool's LONG latency-class timeout.
    resources_timeout_s = 600
