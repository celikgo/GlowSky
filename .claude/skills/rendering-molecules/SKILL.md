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
d.drawOptions().useAvalonAtomPalette()    # -> CPK_2D
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
| Avalon (the print convention) | worst case 4.00:1 | C/H **1.27:1**, N **1.92:1** |

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

## Two ways an element palette fails, and both are gated

**Illegible** and **indistinguishable** are different defects, and a contrast
floor only catches the first.

`CPK_2D` is RDKit's **Avalon** palette, not its familiar default. The default has
yellow sulfur and cyan fluorine and four colours that are illegible on white
(S 1.72:1, F 1.97:1, Cl 2.16:1, P 2.52:1). Avalon clears 3:1 everywhere, worst
case oxygen at 4.00:1 — and pays for it in hue:

| pair | CIE76 dE | |
|---|---|---|
| F / Cl / Br | **0.0** | byte-identical `#007F00` |
| P vs I | 23.5 | both purple |

Sulfur is brown here, not yellow. If that surprises you, that is the trade, and
`cpk.ts` carries the reasoning: a 2D depiction draws the atom **symbol** as well,
so identity is not lost — an F is labelled F — and colour is a redundant second
channel that this palette spends to make the first one legible.

Two ratchets in `scripts/check_design_tokens.py` keep both honest:

- `CPK_2D_BELOW_FLOOR` — **empty**, and that is the mechanism working, not the
  absence of one. An element added below 3:1 fails until somebody writes down its
  number and why it is acceptable. A listed one getting *worse* also fails, and
  means the ground moved, because the colours do not.
- `CPK_2D_INDISTINGUISHABLE` — the four collisions above, with their measured dE.
  A **fourth** element joining the green pile fails. A published collision
  getting closer fails. An entry that stops being true must be removed, because a
  published defect that no longer exists is its own false claim.

If you need a fifth halogen, or an element in the purple range, you will hit the
second ratchet. That is the point: pick a colour that separates, or publish the
collision with its number.

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
- **Adding an element colour without checking it against the others.** Clearing
  the contrast floor is half the job; a new green that nobody can tell from
  chlorine is the other half, and the second ratchet will say so.

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
