"""THY accelerator product #3 — Cargo Dimensioning, as a Glowsky container tool.

In the nakitte-carbon ULD line an OPUS vision model *measures* a cargo piece from a
photo (advisory, human-confirmed); deterministic code then computes the **billable**
figure. Per ADR-140, the model never emits the chargeable weight — code does. This tool
packages exactly that deterministic core: given dimensions + actual weight it returns the
IATA volumetric and chargeable weight. Plug a real measurement model in upstream; this
tool stays the trustworthy, reproducible billing computation.

Glowsky tool ABI: read one JSON object from stdin, write {"ok", result|error} to stdout.
"""
import json
import sys

# IATA air-cargo volumetric divisor: 6000 cm³/kg (= 1 m³ → 166.67 kg).
DEFAULT_DIVISOR_CM3_PER_KG = 6000


def chargeable_weight(
    length_cm: float, width_cm: float, height_cm: float, actual_weight_kg: float,
    divisor: float = DEFAULT_DIVISOR_CM3_PER_KG, pieces: int = 1,
) -> dict:
    for name, v in {"length_cm": length_cm, "width_cm": width_cm,
                    "height_cm": height_cm, "actual_weight_kg": actual_weight_kg}.items():
        if v is None or v < 0:
            raise ValueError(f"{name} must be a non-negative number")
    if divisor <= 0:
        raise ValueError("divisor must be positive")
    if pieces < 1:
        raise ValueError("pieces must be >= 1")

    volume_cm3 = length_cm * width_cm * height_cm * pieces
    volumetric = round(volume_cm3 / divisor, 3)
    actual = round(actual_weight_kg, 3)
    chargeable = max(actual, volumetric)
    return {
        "volume_cm3": round(volume_cm3, 3),
        "volumetric_weight_kg": volumetric,
        "actual_weight_kg": actual,
        "chargeable_weight_kg": chargeable,
        # Which figure the carrier bills on — the larger of the two (IATA rule).
        "basis": "volumetric" if volumetric > actual else "actual",
        "divisor_cm3_per_kg": divisor,
        "pieces": pieces,
    }


def main() -> None:
    try:
        a = json.load(sys.stdin)
        result = chargeable_weight(
            length_cm=a["length_cm"], width_cm=a["width_cm"], height_cm=a["height_cm"],
            actual_weight_kg=a["actual_weight_kg"],
            divisor=a.get("divisor", DEFAULT_DIVISOR_CM3_PER_KG),
            pieces=a.get("pieces", 1),
        )
        json.dump({"ok": True, "result": result}, sys.stdout)
    except Exception as exc:  # handled failure -> ok:false (ABI contract)
        json.dump({"ok": False, "error": str(exc)}, sys.stdout)


if __name__ == "__main__":
    main()
