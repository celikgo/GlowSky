import { useMemo } from "react";
import { useRDKit } from "../hooks/useRDKit";
import { useTheme } from "../hooks/useTheme";
import { CPK_2D_RDKIT, MOL_CANVAS, MOL_LABEL, hexToRgbFloat } from "../theme/cpk";
import { readToken } from "../theme/theme";

/**
 * A 2D depiction of a SMILES string, drawn with RDKit-JS.
 *
 * The atom colours are CPK and do not change with the theme — see
 * `src/theme/cpk.ts` for why that is a chemistry rule and not a style one, and
 * why it forces the drawing surface to stay light in every theme too. What
 * does follow the theme is everything around the drawing: the card, the
 * border, the loading placeholder and the "no depiction" state.
 *
 * Invalid structures (shouldn't happen for firewalled candidates, but might
 * for free-typed input) degrade to a small placeholder rather than throwing.
 */
export function MoleculeStructure({
  smiles,
  width = 280,
  height = 170,
}: {
  smiles: string;
  width?: number;
  height?: number;
}) {
  const rdkit = useRDKit();
  // Subscribed so the depiction is redrawn when the theme changes. The atom
  // colours are the same either way; --mol-label is a token and could move.
  const theme = useTheme();

  const svg = useMemo(() => {
    if (!rdkit) return null;
    const mol = rdkit.get_mol(smiles);
    if (!mol) return null;
    try {
      if (!mol.is_valid()) return null;
      // readToken() is empty under vitest, where CSS is not processed; cpk.ts
      // holds the same two values and CI fails if they disagree with the tokens.
      const label = hexToRgbFloat(readToken("--mol-label") || MOL_LABEL);
      const canvas = hexToRgbFloat(readToken("--mol-canvas") || MOL_CANVAS);
      return mol.get_svg_with_highlights(
        JSON.stringify({
          width,
          height,
          backgroundColour: [...canvas, 1],
          // Not an element colour: the legend and any atom annotations.
          legendColour: [...label, 1],
          annotationColour: [...label, 1],
          bondLineWidth: 1.1,
          atomColourPalette: CPK_2D_RDKIT,
        }),
      );
    } finally {
      mol.delete(); // free the WASM-side molecule
    }
  }, [rdkit, smiles, width, height, theme]);

  if (!rdkit) {
    return <div className="molstruct molstruct--loading" style={{ height }} />;
  }
  if (!svg) {
    return (
      <div className="molstruct molstruct--empty" style={{ height }}>
        no depiction
      </div>
    );
  }
  return (
    <div
      className="molstruct molstruct--drawn"
      style={{ height }}
      // RDKit-generated SVG; the input is a SMILES string, output is sanitized vector markup.
      dangerouslySetInnerHTML={{ __html: svg }}
    />
  );
}