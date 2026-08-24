---
name: rendering-molecules
description: Use when touching how a structure is drawn — the 2D depiction (MoleculeStructure, RDKit-JS), the 3D viewers (Molecule3D, DockingPose3D, 3Dmol.js), the Ketcher editor surface, atom or bond colours, or anything that would change what a chemist sees. Covers why element colours are data rather than theme, the depiction conventions this app holds to, and what an LLM must never infer about a structure. Triggers on "molecule rendering", "depiction", "structure image", "atom colours", "CPK", "RDKit draw", "3Dmol", "docking pose", "Ketcher", "the molecule looks wrong", "SMILES to image".
---

# Rendering molecules

A depiction is not decoration. It is the readout a chemist checks a structure
against, and if it is wrong, or subtly re-coloured, they will believe it before
they believe the SMILES. This skill governs every change to how a structure is
drawn.

## When to use this skill

- Changing `components/MoleculeStructure.tsx`, `Molecule3D.tsx`,
  `DockingPose3D.tsx`, `MoleculeDepiction.tsx`, `KetcherEditor.tsx` or
  `lib/mol3d.ts`.
- Adding an element to a palette, or a highlight, or an atom label.
- Answering "why is the structure on a white card in dark mode?"
- Any change where a colour and a chemical meaning are in the same sentence.

## When NOT to use this skill

- Changing the card, border, badge or placeholder **around** a depiction. That
  is `updating-design-tokens`.
- Changing what a tool computes. Nothing here touches chemistry.

## Rule 1 — element colours are data, not theme

Oxygen is red, nitrogen is blue, sulfur is yellow. A chemist reads those as
identity, at a glance, before reading a single atom label. **A theme must never
re-tint them.**

This is not hypothetical. The version this replaced held a single
`DARK_DRAW_OPTIONS` constant in which oxygen was `#ff7373` and nitrogen
`#6ba3ff` — CPK hues lightened until they read well on the Dim surface. Every
molecule in the app was drawn in a palette adjusted to suit the chrome.

The tables live in `apps/desktop/src/theme/cpk.ts`, which is the **only** file
besides `tokens.css` that `scripts/check_design_tokens.py` allows a raw colour
literal, and the file says why in its header. Both tables are read out of RDKit
2026.03.5's own shipped palettes rather than transcribed from a web page:

```python
from rdkit.Chem.Draw import rdMolDraw2D
d = rdMolDraw2D.MolDraw2DSVG(200, 200)
d.drawOptions().useDefaultAtomPalette()   # -> CPK_2D
d.drawOptions().useCDKAtomPalette()       # -> CPK_3D
d.drawOptions().getAtomPalette()
```

## Rule 2 — the drawing ground does not follow the theme either

This is the part that surprises people, and it follows from a measurement
rather than a preference. **No published element palette is legible on both a
light and a dark ground:**

| palette | on white | on the dim surface |
|---|---|---|
| Jmol / CPK (the screen convention) | H **1.00:1**, S **1.07:1**, Cl **1.55:1** | worst case 2.11:1 |
| RDKit 2D (the print convention) | worst case 1.72:1 | C/H **1.27:1**, N **1.92:1** |

Since the element colours cannot move, the ground is what stays put.
`--mol-canvas` (2D) and `--viewer-canvas` (3D) are **identical in all three
themes**, each pinned to the ground its palette is defined against, and CI fails
if a theme moves either. Everything around the drawing themes normally.

Two consequences worth stating plainly:

- A structure is drawn on a light ground even in `dim` and `lights-out`. That is
  also what the app already did for Ketcher, and it is what a chemist wants: a
  depiction they can paste into a slide or a paper without inverting it.
- The 3D viewport is dark even in the `light` theme, because Jmol's palette is
  only legible there.

`cpk.ts` also exports `MOL_CANVAS`, `MOL_LABEL` and `VIEWER_CANVAS`, because the
viewers paint surfaces CSS cannot reach — RDKit serialises a background into its
SVG and 3Dmol wants a packed integer. Those constants duplicate the tokens, and
CI fails if the two disagree, so the duplication cannot rot.

## Rule 3 — carbon is the one that may move, and only for one reason

Carbon is the skeleton. In a docking figure, cyan carbon on the ligand against a
spectrum-coloured receptor is the standard way a pose separates ligand from
protein — and there the colour is carrying *which molecule is this*, not *which
element is this*. `LIGAND_CARBON` in `cpk.ts` is that, and it is the only
element colour in the app with a licence to differ.

Every heteroatom keeps CPK in that view. If you find yourself overriding a
heteroatom, stop: you are encoding something in a channel that already means
something else.

## Rule 4 — everything that is not element identity is a token

Ground, bond strokes on a light ground, the legend, atom annotations, the
receptor pocket surface, the selection highlight, the loading shimmer, the "no
depiction" placeholder. All of these are `var(--…)` and all of them must stay
legible in every theme. `--viewer-surface` was the last raw hex in any `.tsx` —
`#8b98a5`, `--text-secondary` restated as a JS string.

## Published, not fixed

Four colours in `CPK_2D` fall below the 3:1 floor against `--mol-canvas`:
sulfur 1.72:1, fluorine 1.97:1, chlorine 2.16:1, phosphorus 2.52:1.

They are **not adjusted**, and this is the repository's usual answer to an
uncomfortable measurement — the same answer `docs/VALIDATION.md` gives about the
1HSG re-docking benchmark. The colour is the element's identity; the identity is
also carried by the atom symbol drawn beside it, so what is lost is some of the
colour's legibility, not the information. RDKit's Avalon palette clears 3:1 for
every element (minimum 4.00:1) by making the halogens one green and sulfur
brown; that trade was measured and declined, because a chemist looking for
yellow sulfur is the reason the colours exist.

`CPK_2D_BELOW_FLOOR` in `scripts/check_design_tokens.py` records the four
ratios. A fifth element dropping below the floor fails. One of these four
getting *worse* fails, and it means the ground moved, because the colours do not.

## What an LLM must never infer here

The house rule is that LLMs plan and explain while deterministic tools compute,
and depiction is squarely on the deterministic side.

- **Never write a SMILES, an InChI or a molfile from memory into code, a test
  fixture or a comment.** Structures come from RDKit, from the API, or from the
  user. A plausible-looking SMILES that is the wrong molecule is the single
  worst defect this app can ship, and it is invisible in review.
- **Never hand-compute 2D or 3D coordinates.** 2D layout is RDKit's; 3D comes
  from `POST /molecules/conformer` (ETKDG + MMFF), server-side.
- **Never assert what a structure looks like** — a ring count, a stereocentre,
  an atom's position in the drawing — without computing it. `mol.is_valid()`
  before anything else; an invalid structure degrades to the placeholder rather
  than throwing.
- **Never recall an element's CPK colour.** Read it from `cpk.ts`, which read it
  from RDKit.
- **Never invent a colour convention.** If a change needs a new visual encoding
  (a score ramp, a heat map, a highlight scheme), that is a product decision
  about what the colour *means*, and it needs a legend before it needs a palette.

## What the app deliberately does not colour

Do not add these without deciding what the colour would mean:

- **There is no docking-score legend and no score-to-colour mapping.** Affinity
  is plain text in a plain table. A ramp over a Vina score would imply a
  calibration that does not exist — see `docs/VALIDATION.md`, where that score
  is published as *not* an affinity.
- **Numeric properties are uncoloured** — MW, logP, TPSA, QED are neutral chips
  with no thresholds.
- **The one value-driven colour is the sign of a delta** in `SarScreen`
  (`datatable__pos` / `datatable__neg`). It encodes sign, not desirability, and
  it has no legend. That is a known wart, recorded in
  `docs/14-design-system.md` §5, not something to imitate.

## Common mistakes

- **Lightening a heteroatom so it reads on a dark card.** The bug this system
  replaced.
- **Theming `--mol-canvas`.** CI will stop you; `cpk.ts` explains why.
- **Passing no `colorscheme` to 3Dmol** and relying on its implicit default.
  That is how the 2D and 3D views of the same molecule came to disagree —
  RDKit's custom palette in one, 3Dmol's built-in Jmol in the other. State it.
- **Forgetting that a WebGL canvas cannot inherit a CSS background.** Both 3D
  components subscribe to `useTheme()` and re-drive `setBackgroundColor`; a new
  viewer must too.
- **Leaving `theme` out of a `useMemo`/`useEffect` dependency list.** The
  depiction is cached; without it the old SVG survives a theme change.
- **Adjusting an element colour to make a contrast check pass.** The check is
  there to tell you the ground moved.

## Reference

- `apps/desktop/src/theme/cpk.ts` — both tables, the grounds, the measurements.
- `apps/desktop/src/components/MoleculeStructure.tsx` — 2D, RDKit-JS.
- `apps/desktop/src/components/MoleculeStructure.test.tsx` — asserts the palette
  is byte-identical under every theme.
- `apps/desktop/src/lib/mol3d.ts` — `elementColorscheme()`, `viewerBackground()`.
- `apps/desktop/src/components/Molecule3D.tsx`, `DockingPose3D.tsx` — 3Dmol.
- `docs/14-design-system.md` §4 — the measurements, in a table.
- `docs/05-technical-architecture.md` §1 — RDKit-JS / Ketcher / 3Dmol and the
  server-assisted conformer.
- `.claude/skills/updating-design-tokens` — everything around the drawing.
- There is **no image-diff or visual-regression suite** for depictions. What is
  checked is the palette and the drawing options, not the pixels.
