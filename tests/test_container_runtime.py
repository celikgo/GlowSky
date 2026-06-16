"""Container-tool runtime + manifest loading (infra-free via an injected runner)."""
import json
from pathlib import Path

import pytest

from services.tools.context import ExecutionContext
from services.tools.executor import ToolExecutionService
from services.tools.manifest import (
    load_container_tools,
    load_manifest_file,
    spec_from_manifest,
)
from services.tools.registry import ToolRegistry
from services.tools.runtimes.container import (
    ContainerRuntime,
    ContainerToolError,
    RunOutcome,
)
from services.tools.spec import Egress, Resources, Runtime

EXAMPLE_DIR = Path(__file__).resolve().parents[1] / "examples" / "tools"
MANIFEST = EXAMPLE_DIR / "molecular_formula" / "glowsky-tool.yaml"
ADMET_MANIFEST = EXAMPLE_DIR / "admet_ai" / "glowsky-tool.yaml"


def fake_runner(result: dict | None = None, *, rc: int = 0, stdout=None, timed_out=False):
    captured = {}

    def runner(argv, stdin_text, timeout_s):
        captured["argv"] = argv
        captured["stdin"] = stdin_text
        captured["timeout"] = timeout_s
        out = stdout if stdout is not None else json.dumps({"ok": True, "result": result or {}})
        return RunOutcome(returncode=rc, stdout=out, stderr="", timed_out=timed_out)

    runner.captured = captured
    return runner


def test_sandbox_command_has_isolation_flags():
    rt = ContainerRuntime(runner=fake_runner({"x": 1}))
    argv = rt.build_command("img:1", Resources(cpu=2, mem_mb=512, timeout_s=30), Egress.NONE, "65534:65534")
    joined = " ".join(argv)
    for flag in ["--rm", "--read-only", "--cap-drop ALL", "--security-opt no-new-privileges",
                 "--pids-limit", "--memory 512m", "--cpus 2", "--network none", "--user 65534:65534"]:
        assert flag in joined
    # The image is positional after an explicit `--` terminator (no flag-injection via image ref).
    assert argv[-2:] == ["--", "img:1"]


def test_network_fails_closed_for_non_none_egress():
    """H2: ALLOWLIST has no proxy yet, so it must NOT fall through to the default bridge —
    every egress class is denied the network until a governed proxy ships."""
    rt = ContainerRuntime(runner=fake_runner({"x": 1}))
    res = Resources(cpu=1, mem_mb=256, timeout_s=10)
    for egress in (Egress.NONE, Egress.ALLOWLIST):
        argv = rt.build_command("img:1", res, egress, "65534:65534")
        assert "--network" in argv and argv[argv.index("--network") + 1] == "none", egress


def test_run_passes_args_on_stdin_and_returns_result():
    runner = fake_runner({"formula": "C6H6", "exact_mass": 78.0468})
    rt = ContainerRuntime(runner=runner)
    out = rt.run(image="img:1", args={"canonical_smiles": "c1ccccc1"}, resources=Resources())
    assert out == {"formula": "C6H6", "exact_mass": 78.0468}
    assert json.loads(runner.captured["stdin"]) == {"canonical_smiles": "c1ccccc1"}


def test_run_raises_on_nonzero_exit():
    rt = ContainerRuntime(runner=fake_runner(rc=1, stdout="boom"))
    with pytest.raises(ContainerToolError):
        rt.run(image="img:1", args={}, resources=Resources())


def test_run_raises_on_timeout():
    rt = ContainerRuntime(runner=fake_runner(timed_out=True))
    with pytest.raises(ContainerToolError, match="timed out"):
        rt.run(image="img:1", args={}, resources=Resources(timeout_s=5))


def test_run_raises_on_tool_reported_failure():
    rt = ContainerRuntime(runner=fake_runner(stdout=json.dumps({"ok": False, "error": "bad smiles"})))
    with pytest.raises(ContainerToolError, match="bad smiles"):
        rt.run(image="img:1", args={}, resources=Resources())


def test_run_raises_on_non_json_output():
    rt = ContainerRuntime(runner=fake_runner(stdout="not json at all"))
    with pytest.raises(ContainerToolError, match="non-JSON"):
        rt.run(image="img:1", args={}, resources=Resources())


def test_manifest_parses_to_container_spec():
    m = load_manifest_file(MANIFEST)
    spec = spec_from_manifest(m, ContainerRuntime(runner=fake_runner({})))
    assert spec.name == "molecular_formula"
    assert spec.runtime == Runtime.CONTAINER
    assert spec.env_digest == m.image
    assert spec.compute_class.value == "cpu_heavy"


def test_container_tool_runs_through_executor_with_provenance():
    """The executor treats a container tool exactly like a built-in: cache + provenance."""
    runner = fake_runner({"formula": "C2H6O", "exact_mass": 46.0419, "heavy_atoms": 3})
    reg = ToolRegistry()
    reg.register(spec_from_manifest(load_manifest_file(MANIFEST), ContainerRuntime(runner=runner)))
    svc = ToolExecutionService(reg)

    res = svc.execute("molecular_formula", {"canonical_smiles": "CCO"}, ExecutionContext())
    assert res.output["formula"] == "C2H6O"
    assert res.record.tool == "molecular_formula" and res.record.cache_hit is False
    # Second identical call is served from cache (deterministic tool).
    assert svc.execute("molecular_formula", {"canonical_smiles": "CCO"}).record.cache_hit is True


def test_load_container_tools_registers_from_dir():
    reg = ToolRegistry()
    loaded = load_container_tools(reg, EXAMPLE_DIR, ContainerRuntime(runner=fake_runner({})))
    assert "molecular_formula" in loaded
    assert reg.resolve("molecular_formula").runtime == Runtime.CONTAINER


def test_load_container_tools_missing_dir_is_safe():
    assert load_container_tools(ToolRegistry(), "/nonexistent/path") == []


# --- The real ADMET backend, as a container tool (infra-free: fake runner) ---

def test_admet_manifest_parses_to_container_spec():
    m = load_manifest_file(ADMET_MANIFEST)
    spec = spec_from_manifest(m, ContainerRuntime(runner=fake_runner({})))
    assert spec.name == "admet_ai"
    assert spec.runtime == Runtime.CONTAINER
    assert spec.category.value == "property"
    assert spec.compute_class.value == "cpu_heavy"
    assert spec.resources.timeout_s == 300


def test_admet_tool_runs_through_executor():
    fake_predictions = {
        "backend": "admet-ai", "n_endpoints": 3,
        "predictions": {"Solubility_AqSolDB": -2.1, "hERG": 0.08, "BBB_Martins": 0.91},
    }
    runner = fake_runner(fake_predictions)
    reg = ToolRegistry()
    reg.register(spec_from_manifest(load_manifest_file(ADMET_MANIFEST), ContainerRuntime(runner=runner)))
    svc = ToolExecutionService(reg)

    res = svc.execute("admet_ai", {"canonical_smiles": "CCO", "endpoints": ["hERG"]})
    assert res.output["backend"] == "admet-ai"
    assert "hERG" in res.output["predictions"]
    # args (incl. endpoint filter) are passed through the ABI on stdin
    assert json.loads(runner.captured["stdin"]) == {"canonical_smiles": "CCO", "endpoints": ["hERG"]}
