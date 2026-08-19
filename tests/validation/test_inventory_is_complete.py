"""The unvalidated list must not fall behind the code.

docs/VALIDATION.md is only honest if its `Unvalidated` table is complete. The failure
mode it exists to prevent is a slow one: someone adds a predictive tool, the document
is not updated, and a capability with no benchmark behind it quietly stops being
listed as having no benchmark. Nothing about that failure is visible in a diff.

So the inventory is checked against the live tool registry and the live ADMET backend
on every run. A new predictive capability fails here until it is either validated or
explicitly listed as unvalidated. Both are acceptable answers; silence is not.
"""
from __future__ import annotations

from services.chemistry.adapters.admet_rdkit import RDKitQSPRADMET
from services.tools.catalog import build_default_registry
from tests.validation.report import CAPABILITY_INVENTORY

#: Tool names that compute an exact property of the graph rather than predicting
#: anything — molecular weight, a canonical SMILES, a substructure match. They have no
#: predictive uncertainty to validate, so they are out of scope for this inventory.
#: Adding a name here is a claim that the tool is DETERMINISTIC, not a way to opt a
#: predictor out of being listed.
_DETERMINISTIC_TOOLS = {
    "validate_molecule",
    "compute_descriptors",
    "profile_molecule",
    "druglikeness",
    "structural_alerts",
    "fingerprint",
    "tanimoto_similarity",
    "bulk_similarity",
    "substructure_search",
    "murcko_scaffold",
    "matched_pairs",
    "sar_transforms",
    "generate_analogs",
    "bioisosteric_replacement",
    "generate_conformers",
    "medchem_rules",
}

#: Predictive tools -> the inventory entry that must cover them.
_PREDICTIVE_TOOLS = {
    "sa_score": "Synthetic accessibility (SA score)",
    "synthesizability": "Synthetic accessibility (SA score)",
    "retrosynthesize": "Retrosynthesis — template disconnections",
    "mpo_score": "MPO desirability score",
    "predict_admet": "ADMET — aqueous solubility (logS)",
    "dock": "Docking — re-docking a crystallographic pose",
}


def test_every_registered_tool_is_classified():
    """No tool may be neither deterministic nor predictive — that is how one gets missed."""
    registered = {spec.name for spec in build_default_registry().list()}
    classified = _DETERMINISTIC_TOOLS | set(_PREDICTIVE_TOOLS)
    unclassified = registered - classified
    assert not unclassified, (
        f"tools registered but not classified as deterministic or predictive: "
        f"{sorted(unclassified)}. Add each to _DETERMINISTIC_TOOLS (if it computes an "
        f"exact property) or to _PREDICTIVE_TOOLS plus CAPABILITY_INVENTORY in "
        f"tests/validation/report.py (if it predicts something)."
    )


def test_every_predictive_tool_has_an_inventory_entry():
    missing = {
        tool: capability
        for tool, capability in _PREDICTIVE_TOOLS.items()
        if capability not in CAPABILITY_INVENTORY
    }
    assert not missing, (
        f"predictive tools whose capability is absent from CAPABILITY_INVENTORY: {missing}. "
        f"docs/VALIDATION.md would omit them from the Unvalidated table."
    )


def test_every_admet_endpoint_has_an_inventory_entry():
    """Each ADMET endpoint is a separate claim and needs a separate line.

    'ADMET' as one row would let a validated solubility model vouch for six
    unvalidated ones, which is exactly the flattening the whole design avoids.
    """
    expected = {
        "solubility": "ADMET — aqueous solubility (logS)",
        "logd": "ADMET — logD7.4",
        "herg": "ADMET — hERG liability",
        "cyp3a4": "ADMET — CYP3A4 substrate likelihood",
        "metabolic_stability": "ADMET — metabolic stability",
        "ppb": "ADMET — plasma protein binding",
        "bbb": "ADMET — blood-brain barrier penetration",
    }
    assert set(RDKitQSPRADMET.endpoints) == set(expected), (
        "the ADMET backend's endpoints changed; update this mapping and "
        "CAPABILITY_INVENTORY so docs/VALIDATION.md keeps listing every endpoint"
    )
    for endpoint, capability in expected.items():
        assert capability in CAPABILITY_INVENTORY, (
            f"ADMET endpoint {endpoint!r} has no entry in CAPABILITY_INVENTORY"
        )
