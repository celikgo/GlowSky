"""3D conformer generation (ETKDG) — a real CPU_HEAVY, SEEDED tool.

Exercises the slow-path / worker-pool routing honestly (no fabrication): embeds
conformers, MMFF-optimizes, and reports energies. Heavy enough to belong off the
request thread at scale."""
from __future__ import annotations

from rdkit import Chem
from rdkit.Chem import AllChem


def generate_conformers(canonical_smiles: str, n: int = 5, seed: int = 0xC0FFEE) -> dict:
    mol = Chem.MolFromSmiles(canonical_smiles)
    if mol is None:
        raise ValueError(f"invalid SMILES: {canonical_smiles!r}")
    mol = Chem.AddHs(mol)

    params = AllChem.ETKDGv3()
    params.randomSeed = seed
    conf_ids = list(AllChem.EmbedMultipleConfs(mol, numConfs=n, params=params))

    energies: list[float] = []
    for cid in conf_ids:
        ff = AllChem.MMFFGetMoleculeForceField(
            mol, AllChem.MMFFGetMoleculeProperties(mol), confId=cid
        )
        if ff is not None:
            ff.Minimize()
            energies.append(round(ff.CalcEnergy(), 3))

    return {
        "n_requested": n,
        "n_generated": len(conf_ids),
        "seed": seed,
        "energies_kcal_mol": sorted(energies),
        "lowest_energy": min(energies) if energies else None,
    }
