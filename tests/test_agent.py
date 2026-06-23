"""The end-to-end design loop (offline, via the mock provider)."""
from services.agent.orchestrator import DesignOrchestrator
from services.chemistry.validation import validate_and_canonicalize


async def test_design_loop_end_to_end():
    orch = DesignOrchestrator()  # mock gateway by default
    result = await orch.run(
        goal="make 10 analogs with MW<300, logP 1-3, no PAINS, drug-like",
        seed_smiles="c1ccccc1C(=O)O",
    )

    # Plan was extracted from the goal.
    assert result.plan.max_analogs == 10
    assert result.plan.constraints.mw_max == 300.0
    assert result.plan.constraints.exclude_pains is True

    # Candidates were generated, profiled, and every one is a valid structure.
    assert len(result.candidates) > 0
    for c in result.candidates:
        assert validate_and_canonicalize(c.smiles).valid
        assert "mw" in c.properties and "qed" in c.properties

    # Filtering was applied per the constraints.
    for c in result.candidates:
        if c.passed_filters:
            assert c.properties["mw"] <= 300.0
            assert c.properties["logp"] <= 3.0
            assert c.properties["has_pains"] is False

    # Ranking: passing candidates sort ahead; sorted by score within. The score is the MPO
    # desirability (medicinal-chemistry ranking), surfaced on each candidate's properties.
    for c in result.candidates:
        assert "mpo" in c.properties and 0.0 <= c.properties["mpo"] <= 1.0
        assert c.score == c.properties["mpo"]
    passed = [c for c in result.candidates if c.passed_filters]
    assert passed == sorted(passed, key=lambda c: c.score, reverse=True)

    # Provenance: a full trace and resolved (secret-free) models. Generation runs both
    # strategies — R-group enumeration and bioisosteric/scaffold-hop replacement.
    assert [t.tool for t in result.trace] == [
        "validate_molecule",
        "generate_analogs",
        "bioisosteric_replacement",
        "profile_molecule",
    ]
    assert result.models_used["reasoning"] == "mock/mock"
    assert result.explanation


async def test_design_loop_rejects_invalid_seed():
    orch = DesignOrchestrator()
    try:
        await orch.run(goal="make analogs", seed_smiles="not-a-molecule((")
        assert False, "should have raised"
    except ValueError:
        pass
