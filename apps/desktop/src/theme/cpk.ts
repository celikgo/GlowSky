/**
 * Element colours. This file is chemical data, not design.
 *
 * A chemist reads atom colour as identity: oxygen is red, nitrogen is blue,
 * sulfur is yellow. Those are not decisions this project gets to make, and a
 * theme must never re-tint them — a molecule that changes colour when the app
 * changes colour is a molecule saying something different. `scripts/
 * check_design_tokens.py` exempts this one file from the "no raw colour
 * literal" rule for exactly that reason, and gates the values below instead.
 *
 * WHY THERE ARE TWO TABLES. The CPK convention has a print rendering and a
 * screen rendering, and both are needed because neither is legible on the
 * other's ground. Measured, on the two grounds this app draws on:
 *
 *   - the screen (Jmol) table on white: hydrogen 1.00:1, sulfur 1.07:1,
 *     chlorine 1.55:1 — several elements are simply invisible;
 *   - the print table on the dim surface: carbon 1.27:1, nitrogen 1.92:1 —
 *     the skeleton disappears.
 *
 * So there is no single element palette that survives a theme switch. That is
 * the finding that fixes the design: the GROUND a molecule is drawn on does
 * not follow the theme either. `--mol-canvas` and `--viewer-canvas` in
 * tokens.css are identical in all three themes, each pinned to the ground its
 * palette is defined against. Everything around the drawing — the card, the
 * border, the placeholder, the legend — themes normally.
 *
 * PROVENANCE. Both tables are read out of RDKit 2026.03.5's own shipped
 * palettes rather than transcribed from a web page:
 *
 *     from rdkit.Chem.Draw import rdMolDraw2D
 *     d = rdMolDraw2D.MolDraw2DSVG(200, 200)
 *     d.drawOptions().useDefaultAtomPalette()   # -> CPK_2D
 *     d.drawOptions().useCDKAtomPalette()       # -> CPK_3D
 *     d.drawOptions().getAtomPalette()
 *
 * WHY CPK_2D IS AVALON AND NOT RDKit's DEFAULT. The default 2D palette is the
 * familiar one — yellow sulfur, cyan fluorine, green chlorine — and four of its
 * colours are illegible on white: sulfur 1.72:1, fluorine 1.97:1, chlorine
 * 2.16:1, phosphorus 2.52:1, all below the 3:1 floor. Avalon clears the floor
 * for every element, minimum 4.00:1 at oxygen.
 *
 * WHAT THAT COSTS, MEASURED. Avalon buys contrast by spending hue, and the bill
 * is specific: fluorine, chlorine and bromine are the SAME green, #007F00 —
 * byte-identical, CIE76 dE 0.0. Phosphorus and iodine are both purple, dE 23.5.
 * So colour no longer separates one halogen from another, and a chemist
 * scanning for "the green one" now has three candidates.
 *
 * Element identity is not lost, because a 2D depiction draws the atom SYMBOL as
 * well: an F is labelled F. Colour here is a redundant second channel, and this
 * palette trades some of that redundancy for a legible first one. That is a
 * real trade with a real cost, and it is an owner decision recorded here rather
 * than a self-evident improvement.
 *
 * Both failure modes are gated in scripts/check_design_tokens.py, so neither can
 * quietly get worse: CPK_2D_BELOW_FLOOR (now empty — nothing ships below 3:1)
 * and CPK_2D_INDISTINGUISHABLE, which lists the collisions above so that a
 * FOURTH element joining the green pile fails a build instead of passing one.
 * See `docs/14-design-system.md` §4 and `.claude/skills/rendering-molecules`.
 */

/**
 * The grounds the two palettes are defined against, restated here because the
 * viewers paint onto surfaces CSS cannot reach — RDKit serialises a background
 * into its SVG, and 3Dmol wants a packed integer for a WebGL clear colour — and
 * because a token read through getComputedStyle is empty under vitest, where
 * stylesheets are not processed. These duplicate --mol-canvas and
 * --viewer-canvas in tokens.css, and scripts/check_design_tokens.py fails if
 * the two ever disagree, so the duplication cannot rot.
 */
export const MOL_CANVAS = "#FFFFFF";
export const VIEWER_CANVAS = "#0D1117";
/** The depiction's legend and annotations — a label, not an element colour,
 *  but drawn on the fixed molecule ground and therefore fixed with it. */
export const MOL_LABEL = "#536471";

/** An element colour, keyed by atomic number as a string (RDKit's key type). */
export type ElementPalette = Readonly<Record<string, string>>;

/**
 * The print/white-ground rendering — RDKit's Avalon 2D palette
 * (`useAvalonAtomPalette()`), chosen over RDKit's default because every colour
 * in it clears 3:1 against white. Used by MoleculeStructure for depictions drawn
 * on `--mol-canvas` (white in every theme). `"-1"` is RDKit's key for "any
 * element not listed". Ratios are against `--mol-canvas`.
 */
export const CPK_2D: ElementPalette = Object.freeze({
  "-1": "#000000", // default / unlisted element
  "1": "#000000", // H  — drawn as part of the skeleton, same as carbon
  "6": "#000000", // C  — the skeleton; bonds inherit it
  "7": "#0000FF", // N   8.59:1  blue
  "8": "#FF0000", // O   4.00:1  red — the palette's worst case
  "9": "#007F00", // F   5.20:1  green, shared with Cl and Br — see the header
  "15": "#7F007F", // P  9.51:1  purple, close to I (dE 23.5)
  "16": "#7F3F00", // S  8.04:1  brown, NOT the familiar yellow — see the header
  "17": "#007F00", // Cl 5.20:1  green, shared with F and Br
  "35": "#007F00", // Br 5.20:1  green, shared with F and Cl
  "53": "#3F007F", // I  13.84:1 dark purple
});

/**
 * The screen/dark-ground rendering — the Jmol CPK table, as RDKit ships it
 * under `useCDKAtomPalette()`. This is also what 3Dmol.js uses by default;
 * passing it explicitly means the 3D viewer's element colours are stated in
 * this repository rather than left implicit inside a vendored bundle, which is
 * what let the 2D and 3D views drift apart in the first place.
 *
 * CPK_3D IS NOT GATED ON CONTRAST, deliberately. WCAG 1.4.11 is a criterion for
 * flat graphics; a 3D atom is a lit sphere with a specular highlight, an outline
 * and depth cues, so its rendered pixels span a range around the base colour and
 * a flat base-vs-ground ratio does not describe what a viewer sees. Applying a
 * text-and-graphics floor to it would be using a number outside its scope and
 * then failing builds on it. The 2D depiction is different: those atom labels
 * really are flat glyphs, and CPK_2D is gated accordingly.
 *
 * The ratios are still measured and PRINTED on every run of
 * scripts/check_design_tokens.py, together with the best ground this table could
 * possibly have, so the picture stays visible and cannot go stale. Two elements
 * come out low — bromine and iodine, both dark colours on a dark ground — and
 * the printed sweep shows there is nowhere to move them: no ground beats 2.69:1
 * worst-case, at pure black, which would also cost a black rectangle inside a
 * themed card. Run `make tokens` for the current numbers rather than trusting
 * the two in this sentence.
 *
 * WHAT IS GATED HERE IS COLLISIONS, and that is the failure mode that matters in
 * 3D: a 3D scene draws NO ATOM LABELS, so colour is the only identity channel.
 * Two elements sharing one loses the information outright, where in the 2D
 * depiction it only makes it harder to read — which is exactly why CPK_2D is
 * allowed to spend hue on contrast and this table is not. 3Dmol's `rasmol`
 * alternative was measured and rejected on that basis: five collisions,
 * including boron and chlorine at the same green.
 */
export const CPK_3D: ElementPalette = Object.freeze({
  H: "#FFFFFF",
  B: "#FFB5B5",
  C: "#909090",
  N: "#3050F8",
  O: "#FF0D0D",
  F: "#90E050",
  P: "#FF8000",
  S: "#C6C62C",
  Cl: "#1F7F1F",
  Br: "#A62929",
  I: "#940094",
});

/**
 * Carbon in a docked ligand, and the one element colour that is allowed to
 * move — because in a docking figure carbon is not carrying identity, it is
 * carrying "this is the ligand, that is the receptor". Cyan carbon against a
 * spectrum-coloured receptor is the standard way that separation is drawn, and
 * it is what a chemist expects to see in a pose. Heteroatoms keep CPK_3D.
 */
export const LIGAND_CARBON = "#00FFFF";

/** `#rrggbb` -> the `[r, g, b]` floats 0–1 that RDKit's MinimalLib expects. */
export function hexToRgbFloat(hex: string): [number, number, number] {
  const h = hex.replace("#", "");
  return [
    parseInt(h.slice(0, 2), 16) / 255,
    parseInt(h.slice(2, 4), 16) / 255,
    parseInt(h.slice(4, 6), 16) / 255,
  ];
}

/** `#rrggbb` -> the packed integer 3Dmol.js's `setBackgroundColor` expects. */
export function hexToInt(hex: string): number {
  return parseInt(hex.replace("#", ""), 16);
}

/** CPK_2D as RDKit MinimalLib's `atomColourPalette` (atomic number -> RGB floats). */
export const CPK_2D_RDKIT: Readonly<Record<string, [number, number, number]>> =
  Object.freeze(
    Object.fromEntries(
      Object.entries(CPK_2D).map(([z, hex]) => [z, hexToRgbFloat(hex)]),
    ) as Record<string, [number, number, number]>,
  );
