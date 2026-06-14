"""Real ADMET backend as a Glowsky container tool — ADMET-AI.

ADMET-AI (Swanson et al., Bioinformatics 2024) is an open, pretrained Chemprop-RDKit
graph neural network predicting ~40 ADMET endpoints from the Therapeutics Data Commons
(solubility, hERG, CYP inhibition, Caco-2, BBB, bioavailability, clearance, half-life…).

Speaks the Glowsky tool ABI: JSON args on stdin -> {"ok", result} on stdout.
Model weights are baked into the image at build time, so it runs with --network none.
"""
import json
import re
import sys


def _to_float(v):
    try:
        return round(float(v), 5)
    except (TypeError, ValueError):
        return v


def main() -> None:
    try:
        args = json.load(sys.stdin)
        smiles = args["canonical_smiles"]
        endpoints = args.get("endpoints")  # optional: substring filters

        # Imported lazily so import errors surface as a clean ABI failure, not a crash.
        from admet_ai import ADMETModel

        model = ADMETModel()
        preds = model.predict(smiles=smiles)  # dict: endpoint -> value (single SMILES)
        preds = {k: _to_float(v) for k, v in preds.items()}

        if endpoints:
            pattern = re.compile("|".join(re.escape(e) for e in endpoints), re.IGNORECASE)
            preds = {k: v for k, v in preds.items() if pattern.search(k)}

        result = {
            "backend": "admet-ai",
            "model": "Chemprop-RDKit (TDC ADMET)",
            "n_endpoints": len(preds),
            "predictions": preds,
        }
        json.dump({"ok": True, "result": result}, sys.stdout)
    except Exception as exc:
        json.dump({"ok": False, "error": str(exc)}, sys.stdout)


if __name__ == "__main__":
    main()
