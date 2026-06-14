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


def conformer_molblock(canonical_smiles: str, seed: int = 0xC0FFEE) -> dict:
    """Embed a single low-energy 3D conformer and return it as an MDL MOL block.

    Powers the desktop 3D viewer: one ETKDG conformer, MMFF-minimized, returned as
    3D coordinates a structure viewer can render directly. Hydrogens are stripped
    after optimization (heavy-atom 3D coords are preserved) for a cleaner depiction.
    """
    mol = Chem.MolFromSmiles(canonical_smiles)
    if mol is None:
        raise ValueError(f"invalid SMILES: {canonical_smiles!r}")
    mol = Chem.AddHs(mol)

    params = AllChem.ETKDGv3()
    params.randomSeed = seed
    if AllChem.EmbedMolecule(mol, params) != 0:
        raise ValueError(f"3D embedding failed for {canonical_smiles!r}")

    energy: float | None = None
    ff = AllChem.MMFFGetMoleculeForceField(mol, AllChem.MMFFGetMoleculeProperties(mol))
    if ff is not None:
        ff.Minimize()
        energy = round(ff.CalcEnergy(), 3)

    mol = Chem.RemoveHs(mol)
    return {
        "molblock": Chem.MolToMolBlock(mol),
        "energy_kcal_mol": energy,
        "seed": seed,
    }
