"""A real, offline ADMET backend built on RDKit descriptors and published QSPR models.

This is a genuine computation — not fabricated values — but it is deliberately honest
about its nature: solubility uses Delaney's **ESOL** model (J. Chem. Inf. Comput. Sci.
2004), BBB uses a TPSA/MW/logP rule, and the toxicity/metabolism endpoints are
lipophilicity- and substructure-based heuristics. Every prediction carries a `method`,
a `confidence`, and an `applicability_domain` flag so the UI can show honest uncertainty
(docs/12 #5). For high-accuracy predictions, register the ADMET-AI container tool
(examples/tools/admet_ai) instead — same adapter seam, GNN-grade numbers.

Enabled via GLOWSKY_ADMET_BACKEND=rdkit; the module default remains "not configured"
so Glowsky never returns ADMET numbers unless a backend is explicitly chosen.
"""
from __future__ import annotations

import math

from rdkit import Chem
from rdkit.Chem import Crippen, Descriptors, rdMolDescriptors

# SMARTS for a likely-basic nitrogen (protonatable amine), excluding amides/anilines/etc.
_BASIC_N = Chem.MolFromSmarts("[NX3;H2,H1,H0;!$(NC=O);!$(N=*);!$([N+]);!$(Nc)]")

# Endpoints this backend can estimate.
_ENDPOINTS = ["solubility", "logd", "herg", "cyp3a4", "metabolic_stability", "ppb", "bbb"]


def _aromatic_proportion(mol: Chem.Mol) -> float:
    heavy = mol.GetNumHeavyAtoms()
    if heavy == 0:
        return 0.0
    aromatic = sum(1 for a in mol.GetAtoms() if a.GetIsAromatic())
    return aromatic / heavy


def _logistic(x: float) -> float:
    return 1.0 / (1.0 + math.exp(-x))


class RDKitQSPRADMET:
    """Deterministic ADMET estimates from RDKit descriptors + published correlations."""

    name = "rdkit-qspr"
    endpoints = _ENDPOINTS

    def predict(self, canonical_smiles: str, endpoints: list[str]) -> dict:
        mol = Chem.MolFromSmiles(canonical_smiles)
        if mol is None:
            raise ValueError(f"RDKitQSPRADMET received invalid SMILES: {canonical_smiles!r}")

        mw = Descriptors.MolWt(mol)
        logp = Crippen.MolLogP(mol)
        tpsa = rdMolDescriptors.CalcTPSA(mol)
        rb = rdMolDescriptors.CalcNumRotatableBonds(mol)
        hbd = rdMolDescriptors.CalcNumHBD(mol)
        arom_rings = rdMolDescriptors.CalcNumAromaticRings(mol)
        ap = _aromatic_proportion(mol)
        has_basic_n = mol.HasSubstructMatch(_BASIC_N) if _BASIC_N is not None else False

        computed = {
            "solubility": lambda: self._solubility(mw, logp, rb, ap),
            "logd": lambda: self._logd(logp),
            "herg": lambda: self._herg(logp, mw, has_basic_n),
            "cyp3a4": lambda: self._cyp3a4(logp, mw),
            "metabolic_stability": lambda: self._metabolic_stability(logp, arom_rings),
            "ppb": lambda: self._ppb(logp),
            "bbb": lambda: self._bbb(tpsa, mw, logp, hbd),
        }

        out: dict = {}
        for ep in endpoints:
            key = ep.strip().lower()
            if key in computed:
                out[key] = computed[key]()
            else:
                out[ep] = {"error": "endpoint not supported by rdkit-qspr backend"}
        return out

    # --- endpoint models ------------------------------------------------------

    @staticmethod
    def _solubility(mw: float, logp: float, rb: int, ap: float) -> dict:
        # Delaney ESOL (2004): logS (mol/L) from MW, cLogP, rotatable bonds, aromatic fraction.
        log_s = 0.16 - 0.63 * logp - 0.0062 * mw + 0.066 * rb - 0.74 * ap
        mg_per_ml = (10 ** log_s) * mw
        in_domain = 100 <= mw <= 600 and -3 <= logp <= 7
        return {
            "value": round(log_s, 2),
            "unit": "logS (mol/L)",
            "mg_per_ml": round(mg_per_ml, 4),
            "method": "ESOL (Delaney 2004)",
            "confidence": "medium" if in_domain else "low",
            "applicability_domain": "in" if in_domain else "out",
        }

    @staticmethod
    def _logd(logp: float) -> dict:
        # Neutral-species proxy: logD7.4 ≈ cLogP. Ionizable groups shift this down; flagged low.
        return {
            "value": round(logp, 2),
            "unit": "logD7.4 (estimated)",
            "method": "Crippen cLogP (neutral proxy)",
            "confidence": "low",
            "applicability_domain": "borderline",
        }

    @staticmethod
    def _herg(logp: float, mw: float, has_basic_n: bool) -> dict:
        # hERG blockade rises with lipophilicity + a basic (protonatable) amine.
        score = _logistic(1.1 * (logp - 3.0) + (1.2 if has_basic_n else -0.3))
        risk = "high" if score >= 0.66 else "medium" if score >= 0.33 else "low"
        return {
            "value": risk,
            "probability": round(score, 2),
            "method": "heuristic (lipophilicity + basic amine)",
            "confidence": "low",
            "applicability_domain": "in" if 150 <= mw <= 600 else "borderline",
        }

    @staticmethod
    def _cyp3a4(logp: float, mw: float) -> dict:
        # CYP3A4 turnover favors larger, lipophilic substrates.
        score = _logistic(0.9 * (logp - 2.8) + 0.004 * (mw - 350))
        risk = "high" if score >= 0.66 else "medium" if score >= 0.33 else "low"
        return {
            "value": risk,
            "probability": round(score, 2),
            "method": "heuristic (size + lipophilicity)",
            "confidence": "low",
            "applicability_domain": "in" if 150 <= mw <= 700 else "borderline",
        }

    @staticmethod
    def _metabolic_stability(logp: float, aromatic_rings: int) -> dict:
        # More lipophilic / aromatic -> generally faster CYP metabolism -> less stable.
        score = _logistic(0.8 * (logp - 3.0) + 0.4 * (aromatic_rings - 2))
        label = "low" if score >= 0.66 else "medium" if score >= 0.33 else "high"
        return {
            "value": label,  # stability label (high = stable)
            "instability_score": round(score, 2),
            "method": "heuristic (lipophilicity + aromaticity)",
            "confidence": "low",
            "applicability_domain": "in",
        }

    @staticmethod
    def _ppb(logp: float) -> dict:
        # Plasma protein binding fraction climbs with lipophilicity.
        fraction = _logistic(0.9 * (logp - 1.0))
        return {
            "value": round(fraction, 3),
            "unit": "fraction bound",
            "method": "heuristic (lipophilicity logistic)",
            "confidence": "low",
            "applicability_domain": "in",
        }

    @staticmethod
    def _bbb(tpsa: float, mw: float, logp: float, hbd: int) -> dict:
        # TPSA/MW/logP/HBD rule of thumb for blood-brain-barrier penetration.
        penetrant = tpsa < 90 and mw < 450 and 1.0 < logp < 4.0 and hbd <= 3
        # Smooth score centered on the TPSA=90 boundary, nudged by lipophilicity.
        score = _logistic((90 - tpsa) / 25.0 + 0.3 * (logp - 2.0))
        return {
            "value": bool(penetrant),
            "probability": round(score, 2),
            "method": "TPSA/MW/logP/HBD rule",
            "confidence": "medium",
            "applicability_domain": "in" if mw < 600 else "out",
        }
