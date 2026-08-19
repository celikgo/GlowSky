"""Generate the repository's social preview image.

The frame shows the premise in one picture: a real structure, the panel of numbers
Glowsky computes for it, and the agent turn that produced them — with the numbers
carrying their uncertainty, because that is the part this project is actually about.

Every value in the image is COMPUTED at generation time by the same code paths the
product uses. Nothing is typed in by hand, which means the picture cannot drift away
from what the software does, and it cannot flatter it either.

    python -m scripts.make_social_preview        # -> assets/social-preview.png

GitHub's social preview is 1280x640. Upload it under
Settings -> General -> Social preview; there is no API for that field.
"""
from __future__ import annotations

import pathlib
import subprocess

from rdkit import Chem
from rdkit.Chem.Draw import rdMolDraw2D

from services.chemistry.adapters.admet_rdkit import RDKitQSPRADMET
from services.chemistry.medchem import mpo_score
from services.chemistry.properties import profile
from services.chemistry.validation import validate_and_canonicalize

ROOT = pathlib.Path(__file__).resolve().parents[1]
OUT_SVG = ROOT / "assets" / "social-preview.svg"
OUT_PNG = ROOT / "assets" / "social-preview.png"

W, H = 1280, 640

# Celecoxib — a real marketed drug, recognisable to the audience, and comfortably
# inside every model's applicability domain so the frame shows the normal case.
SMILES = "Cc1ccc(-c2cc(C(F)(F)F)nn2-c2ccc(S(N)(=O)=O)cc2)cc1"
NAME = "Celecoxib"

# Palette lifted from the desktop app's dark theme (tauri.conf.json backgroundColor).
BG = "#15202B"
PANEL = "#1B2836"
EDGE = "#2A3B4D"
TEXT = "#E6EDF3"
MUTED = "#8FA3B8"
ACCENT = "#26A69A"
WARN = "#E3A008"


def _esc(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _structure_svg(smiles: str) -> str:
    """Render the molecule and return its <svg> inner content, for embedding."""
    mol = Chem.MolFromSmiles(smiles)
    Chem.rdDepictor.Compute2DCoords(mol)
    drawer = rdMolDraw2D.MolDraw2DSVG(420, 250)
    opts = drawer.drawOptions()
    opts.clearBackground = False
    opts.setBackgroundColour((0, 0, 0, 0))
    # Light-on-dark: RDKit defaults to black bonds, invisible on this background.
    opts.setAtomPalette({-1: (0.90, 0.93, 0.95)})
    opts.bondLineWidth = 2
    rdMolDraw2D.PrepareAndDrawMolecule(drawer, mol)
    drawer.FinishDrawing()
    svg = drawer.GetDrawingText()
    # Strip the XML declaration and outer <svg> so it nests inside ours.
    body = svg.split(">", 1)[1] if svg.startswith("<?xml") else svg
    inner = body[body.index(">", body.index("<svg")) + 1 : body.rindex("</svg>")]
    return inner


def build() -> str:
    result = validate_and_canonicalize(SMILES)
    assert result.valid, result.error
    props = profile(result.smiles)
    mpo = mpo_score(result.smiles)
    admet = RDKitQSPRADMET().predict(result.smiles, ["solubility", "herg"])
    sol = admet["solubility"]
    herg = admet["herg"]

    lo, hi = sol["uncertainty"]["interval"]
    rows = [
        ("MW", f"{props['mw']:.2f}", "exact", None),
        ("cLogP", f"{props['logp']:.2f}", "Wildman-Crippen", None),
        ("TPSA", f"{props['tpsa']:.1f} \u00c5\u00b2", "Ertl fragment", None),
        ("QED", f"{props['qed']:.3f}", "Bickerton 2012", None),
        ("MPO (oral)", f"{mpo['score']:.3f}", f"limiting: {mpo['limiting']}", None),
        (
            "Solubility",
            f"{sol['value']:.2f} logS",
            f"95% CI [{lo:.2f}, {hi:.2f}] - ESOL, measured RMSE",
            ACCENT,
        ),
        (
            "hERG",
            f"{herg['value']}",
            f"p={herg['uncertainty']['probability']:.2f} - HEURISTIC, unvalidated",
            WARN,
        ),
    ]

    parts: list[str] = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" '
        f'viewBox="0 0 {W} {H}" font-family="Inter, Helvetica, Arial, sans-serif">',
        f'<rect width="{W}" height="{H}" fill="{BG}"/>',
        # Header. The wordmark and the tagline are on separate lines rather than
        # side by side: "Glowsky" at 42px is wider than any fixed x-offset guessed
        # for the tagline, so sharing a baseline made them overlap.
        f'<text x="56" y="72" fill="{TEXT}" font-size="40" font-weight="700">Glowsky</text>',
        f'<text x="58" y="102" fill="{MUTED}" font-size="20">'
        f'the AI-native workspace for small-molecule drug design</text>',
        f'<text x="58" y="128" fill="{ACCENT}" font-size="19" font-weight="600">'
        f'LLMs reason and explain &#183; deterministic chemistry computes</text>',
        f'<line x1="56" y1="146" x2="{W - 56}" y2="146" stroke="{EDGE}" stroke-width="1"/>',
        # --- agent turn -------------------------------------------------------
        f'<rect x="56" y="166" width="{W - 112}" height="60" rx="10" fill="{PANEL}" '
        f'stroke="{EDGE}"/>',
        f'<text x="76" y="190" fill="{MUTED}" font-size="14" font-weight="600">'
        f'&#9679; chemist</text>',
        f'<text x="76" y="213" fill="{TEXT}" font-size="18">'
        f'"Profile {NAME.lower()} for me - and tell me how much to trust the numbers."</text>',
        # --- structure panel --------------------------------------------------
        f'<rect x="56" y="246" width="470" height="340" rx="12" fill="{PANEL}" '
        f'stroke="{EDGE}"/>',
        f'<text x="80" y="276" fill="{TEXT}" font-size="19" font-weight="600">{NAME}</text>',
        f'<text x="80" y="297" fill="{MUTED}" font-size="12" font-family="monospace">'
        f'{_esc(result.key)}</text>',
        # 420x250 canvas at y=308 ends at 558, clear of the caption at 574 and of the
        # panel edge at 586.
        f'<g transform="translate(81,308)">{_structure_svg(result.smiles)}</g>',
        f'<text x="80" y="574" fill="{MUTED}" font-size="12.5">'
        f'validated &#183; canonicalized &#183; never a model-generated string</text>',
        # --- property panel ---------------------------------------------------
        f'<rect x="550" y="246" width="{W - 606}" height="340" rx="12" fill="{PANEL}" '
        f'stroke="{EDGE}"/>',
        f'<text x="576" y="276" fill="{TEXT}" font-size="19" font-weight="600">'
        f'Computed properties</text>',
    ]

    y = 310
    for label, value, note, colour in rows:
        value_colour = colour or TEXT
        parts += [
            f'<text x="576" y="{y}" fill="{MUTED}" font-size="16">{_esc(label)}</text>',
            f'<text x="742" y="{y}" fill="{value_colour}" font-size="17" '
            f'font-weight="600" font-family="monospace">{_esc(value)}</text>',
            f'<text x="880" y="{y}" fill="{MUTED}" font-size="14">{_esc(note)}</text>',
        ]
        y += 36

    parts += [
        f'<line x1="576" y1="{y - 16}" x2="{W - 82}" y2="{y - 16}" stroke="{EDGE}"/>',
        f'<text x="576" y="{y + 10}" fill="{ACCENT}" font-size="14" font-weight="600">'
        f'Every prediction carries its uncertainty, its applicability domain,</text>',
        f'<text x="576" y="{y + 30}" fill="{ACCENT}" font-size="14" font-weight="600">'
        f'and a citation. What is unvalidated says so.</text>',
        f'<text x="56" y="{H - 22}" fill="{MUTED}" font-size="14">'
        f'RDKit &#183; FastAPI &#183; Tauri &#183; Bring-Your-Own-LLM &#183; self-hostable '
        f'&#183; benchmarks in docs/VALIDATION.md</text>',
        "</svg>",
    ]
    return "\n".join(parts)


def main() -> int:
    OUT_SVG.parent.mkdir(parents=True, exist_ok=True)
    OUT_SVG.write_text(build())
    print(f"wrote {OUT_SVG}")
    try:
        subprocess.run(
            ["rsvg-convert", "-w", str(W), "-h", str(H), "-o", str(OUT_PNG), str(OUT_SVG)],
            check=True, capture_output=True, text=True,
        )
        print(f"wrote {OUT_PNG}")
    except (FileNotFoundError, subprocess.CalledProcessError) as exc:
        print(f"could not rasterise (need rsvg-convert): {exc}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
