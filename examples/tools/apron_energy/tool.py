"""THY accelerator product #1 — Apron Energy, as a Glowsky container tool.

In the nakitte-carbon ULD line, apron energy is a projection over ground-support-equipment
(GSE) activity already captured against ULD movements (ADR-139: a report is a WHERE clause
over data you already post). This tool packages that deterministic roll-up: given apron
movements/GSE runtime, it estimates energy (kWh) and grid CO2 (kg). It fabricates nothing —
with no movements it honestly returns zero (empty until the movement seam feeds it).

Glowsky tool ABI: read one JSON object from stdin, write {"ok", result|error} to stdout.
"""
import json
import sys

# Indicative kWh per movement by GSE class (electric tug/loader/GPU duty cycles). Override
# per record with an explicit "kwh". These are projection defaults, not measured truth.
DEFAULT_KWH_BY_KIND = {
    "tow": 4.5,        # electric tow tractor moving a ULD dolly train
    "load": 2.0,       # belt/high-loader cycle
    "gpu": 8.0,        # ground power unit serving a stand
    "pcair": 6.0,      # pre-conditioned air
}
# TR grid average emission factor (kg CO2e / kWh). Override via grid_factor.
DEFAULT_GRID_FACTOR = 0.42


def project(movements: list[dict], grid_factor: float = DEFAULT_GRID_FACTOR) -> dict:
    if grid_factor < 0:
        raise ValueError("grid_factor must be non-negative")
    total_kwh = 0.0
    by_kind: dict[str, float] = {}
    for m in movements or []:
        kind = m.get("kind", "tow")
        count = m.get("count", 1)
        if count < 0:
            raise ValueError(f"count must be non-negative for kind {kind!r}")
        per = m.get("kwh", DEFAULT_KWH_BY_KIND.get(kind))
        if per is None:
            raise ValueError(f"unknown movement kind {kind!r}; provide an explicit kwh")
        if per < 0:
            raise ValueError("kwh must be non-negative")
        kwh = per * count
        total_kwh += kwh
        by_kind[kind] = round(by_kind.get(kind, 0.0) + kwh, 3)

    total_kwh = round(total_kwh, 3)
    return {
        "energy_kwh": total_kwh,
        "co2e_kg": round(total_kwh * grid_factor, 3),
        "grid_factor_kg_per_kwh": grid_factor,
        "by_kind_kwh": by_kind,
        "movement_records": len(movements or []),
    }


def main() -> None:
    try:
        a = json.load(sys.stdin)
        result = project(a.get("movements", []), grid_factor=a.get("grid_factor", DEFAULT_GRID_FACTOR))
        json.dump({"ok": True, "result": result}, sys.stdout)
    except Exception as exc:  # handled failure -> ok:false (ABI contract)
        json.dump({"ok": False, "error": str(exc)}, sys.stdout)


if __name__ == "__main__":
    main()
