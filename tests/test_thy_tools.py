"""THY accelerator products plugged into Glowsky as container tools.

Two layers, both Docker-free:
  * the `glowsky-tool.yaml` manifests parse + register as logistics ToolSpecs, and
  * each tool.py honors the JSON-stdin/stdout ABI with the right deterministic result
    (run as a subprocess — exactly what the container runtime does, minus the sandbox).
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from services.tools.manifest import (
    load_container_tools,
    load_manifest_file,
    spec_from_manifest,
)
from services.tools.registry import ToolRegistry
from services.tools.runtimes.container import ContainerRuntime
from services.tools.spec import Runtime, ToolCategory

TOOLS_DIR = Path(__file__).resolve().parents[1] / "examples" / "tools"
THY_TOOLS = ("cargo_dimensioning", "damage_detect", "apron_energy")


def _run(tool: str, args: dict) -> dict:
    """Drive a tool's JSON ABI as a subprocess (the container runtime, sans Docker)."""
    proc = subprocess.run(
        [sys.executable, str(TOOLS_DIR / tool / "tool.py")],
        input=json.dumps(args), capture_output=True, text=True, timeout=30,
        # The tool's non-zero exits are part of its ABI and are asserted on below.
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout)


# --- manifests register as logistics tools ------------------------------------


def test_manifests_parse_as_logistics_specs():
    for tool in THY_TOOLS:
        m = load_manifest_file(TOOLS_DIR / tool / "glowsky-tool.yaml")
        assert m.name == tool
        assert m.category == ToolCategory.LOGISTICS
        assert m.egress.value == "none"
        spec = spec_from_manifest(m, ContainerRuntime(runner=lambda *a: None))
        assert spec.runtime == Runtime.CONTAINER and spec.env_digest == m.image


def test_thy_tools_register_from_dir():
    reg = ToolRegistry()
    loaded = load_container_tools(reg, TOOLS_DIR, ContainerRuntime(runner=lambda *a: None))
    for tool in THY_TOOLS:
        assert tool in loaded
        assert reg.resolve(tool).category == ToolCategory.LOGISTICS


# --- #3 Cargo Dimensioning: deterministic IATA chargeable weight (ADR-140) -----


def test_cargo_dimensioning_bills_on_actual_when_heavier():
    r = _run("cargo_dimensioning",
             {"length_cm": 100, "width_cm": 50, "height_cm": 40, "actual_weight_kg": 80})
    assert r["ok"]
    out = r["result"]
    assert out["volumetric_weight_kg"] == 33.333  # 200000 / 6000
    assert out["chargeable_weight_kg"] == 80 and out["basis"] == "actual"


def test_cargo_dimensioning_bills_on_volume_when_bulky():
    r = _run("cargo_dimensioning",
             {"length_cm": 120, "width_cm": 100, "height_cm": 100, "actual_weight_kg": 50})
    out = r["result"]
    assert out["volumetric_weight_kg"] == 200.0  # 1.2e6 / 6000
    assert out["chargeable_weight_kg"] == 200.0 and out["basis"] == "volumetric"


def test_cargo_dimensioning_rejects_bad_input():
    r = _run("cargo_dimensioning",
             {"length_cm": -1, "width_cm": 10, "height_cm": 10, "actual_weight_kg": 5})
    assert r["ok"] is False and "length_cm" in r["error"]


# --- #2 AI Damage Detection: deterministic triage gate -------------------------


def test_damage_triage_routes_by_confidence():
    strong = _run("damage_detect", {"detections": [{"label": "dent", "confidence": 0.92}]})["result"]
    assert strong["decision"] == "damage_suspected" and strong["routed_for_human"] is True
    assert strong["top_label"] == "dent"

    mid = _run("damage_detect", {"detections": [{"confidence": 0.55}]})["result"]
    assert mid["decision"] == "pending_review" and mid["routed_for_human"] is True

    weak = _run("damage_detect", {"detections": [{"confidence": 0.1}]})["result"]
    assert weak["decision"] == "no_damage" and weak["routed_for_human"] is False


def test_damage_triage_empty_is_no_damage():
    out = _run("damage_detect", {"detections": []})["result"]
    assert out["decision"] == "no_damage" and out["n_regions"] == 0 and out["top_label"] is None


# --- #1 Apron Energy: deterministic projection (ADR-139) -----------------------


def test_apron_energy_projects_kwh_and_co2():
    out = _run("apron_energy",
               {"movements": [{"kind": "tow", "count": 2}, {"kind": "gpu"}], "grid_factor": 0.42})["result"]
    assert out["energy_kwh"] == 17.0  # 4.5*2 + 8.0
    assert out["co2e_kg"] == 7.14     # 17.0 * 0.42
    assert out["by_kind_kwh"] == {"tow": 9.0, "gpu": 8.0}


def test_apron_energy_empty_is_zero_not_fabricated():
    out = _run("apron_energy", {"movements": []})["result"]
    assert out["energy_kwh"] == 0.0 and out["co2e_kg"] == 0.0 and out["movement_records"] == 0


def test_apron_energy_unknown_kind_without_kwh_errors():
    r = _run("apron_energy", {"movements": [{"kind": "warp_drive"}]})
    assert r["ok"] is False and "warp_drive" in r["error"]
