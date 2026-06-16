"""THY accelerator product #2 — AI Damage Detection, as a Glowsky container tool.

The nakitte-carbon ULD line already ships vision-based damage detection (Sprint 263):
a model classifies cargo/baggage damage from a photo, then a deterministic gate routes
each finding classify -> pending_review -> human-confirm. The vision inference is
advisory and lives upstream; what's reproducible — and what must never be a model's
free choice — is the **routing decision**. This tool packages that deterministic gate:
given the model's candidate detections, it decides what a human must review.

Glowsky tool ABI: read one JSON object from stdin, write {"ok", result|error} to stdout.
"""
import json
import sys

# Confidence gates. >= confirm -> strong signal; >= review -> needs a human; else clear.
DEFAULT_CONFIRM_THRESHOLD = 0.85
DEFAULT_REVIEW_THRESHOLD = 0.40


def triage(
    detections: list[dict],
    confirm_threshold: float = DEFAULT_CONFIRM_THRESHOLD,
    review_threshold: float = DEFAULT_REVIEW_THRESHOLD,
) -> dict:
    if not 0 <= review_threshold <= confirm_threshold <= 1:
        raise ValueError("require 0 <= review_threshold <= confirm_threshold <= 1")
    regions = []
    for d in detections or []:
        conf = float(d.get("confidence", 0.0))
        if not 0 <= conf <= 1:
            raise ValueError(f"confidence out of range: {conf}")
        regions.append({"label": d.get("label", "damage"), "confidence": round(conf, 4),
                        "bbox": d.get("bbox")})

    top = max(regions, key=lambda r: r["confidence"], default=None)
    top_conf = top["confidence"] if top else 0.0
    if top_conf >= confirm_threshold:
        decision = "damage_suspected"   # strong — still human-confirmed before any claim
    elif top_conf >= review_threshold:
        decision = "pending_review"
    else:
        decision = "no_damage"

    # Never auto-finalizes: anything above the review floor goes to a human (ADR-140 spirit
    # — the model advises, deterministic code decides routing, a person confirms).
    routed_for_human = top_conf >= review_threshold
    return {
        "decision": decision,
        "routed_for_human": routed_for_human,
        "top_label": top["label"] if top else None,
        "top_confidence": top_conf,
        "n_regions": len(regions),
        "regions": regions,
        "thresholds": {"confirm": confirm_threshold, "review": review_threshold},
    }


def main() -> None:
    try:
        a = json.load(sys.stdin)
        result = triage(
            a.get("detections", []),
            confirm_threshold=a.get("confirm_threshold", DEFAULT_CONFIRM_THRESHOLD),
            review_threshold=a.get("review_threshold", DEFAULT_REVIEW_THRESHOLD),
        )
        json.dump({"ok": True, "result": result}, sys.stdout)
    except Exception as exc:  # handled failure -> ok:false (ABI contract)
        json.dump({"ok": False, "error": str(exc)}, sys.stdout)


if __name__ == "__main__":
    main()
