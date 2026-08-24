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
 * KNOWN, PUBLISHED, NOT FIXED. Four colours in CPK_2D fall below 3:1 against
 * white: sulfur 1.72:1, fluorine 1.97:1, chlorine 2.16:1, phosphorus 2.52:1.
 * They are not adjusted. The colour is the element's identity, and the
 * identity is also carried by the atom symbol drawn beside it, so what is lost
 * is some of the colour's legibility, not the information (WCAG 1.4.1 is
 * satisfied; 1.4.11 is not, for those four). RDKit's Avalon palette clears
 * 3:1 for every element — minimum 4.00:1 — by making the halogens one green
 * and sulfur brown; that trade was measured and declined, because a chemist
 * looking for yellow sulfur is the reason the colours exist. The four ratios
 * are gated by `CPK_2D_BELOW_FLOOR` in scripts/check_design_tokens.py, so a
 * fifth element dropping below the floor fails a build. See
 * `docs/14-design-system.md` §4 and `.claude/skills/rendering-molecules`.
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
 * The print/white-ground rendering — RDKit's default 2D palette.
 * Used by MoleculeStructure for depictions drawn on `--mol-canvas` (white in
 * every theme). `"-1"` is RDKit's key for "any element not listed".
 */
export const CPK_2D: ElementPalette = Object.freeze({
  "-1": "#000000", // default / unlisted element
  "1": "#000000", // H  — drawn as part of the skeleton, see the note below
  "6": "#000000", // C  — the skeleton; bonds inherit it
  "7": "#0000FF", // N   8.59:1 on white
  "8": "#FF0000", // O   4.00:1
  "9": "#33CCCC", // F   1.97:1  <- below the 3:1 floor, published, see the header
  "15": "#FF8000", // P  2.52:1  <- below the floor
  "16": "#CCCC00", // S  1.72:1  <- below the floor
  "17": "#00CD00", // Cl 2.16:1  <- below the floor
  "35": "#804C1A", // Br  7.08:1
  "53": "#A11FF0", // I   5.29:1
});

/**
 * The screen/dark-ground rendering — the Jmol CPK table, as RDKit ships it
 * under `useCDKAtomPalette()`. This is also what 3Dmol.js uses by default;
 * passing it explicitly means the 3D viewer's element colours are stated in
 * this repository rather than left implicit inside a vendored bundle, which is
 * what let the 2D and 3D views drift apart in the first place.
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
