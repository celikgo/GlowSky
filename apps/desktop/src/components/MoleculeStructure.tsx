import { useMemo } from "react";
import { useRDKit } from "../hooks/useRDKit";

// Dark-mode depiction: transparent background + a light atom palette. Bonds inherit
// their atoms' colors, so a light carbon (#F2F7F7) yields a light skeleton; heteroatoms
// are lightened so they stay legible on the Dim surface. Colors are RGB floats 0–1.
const LIGHT: [number, number, number] = [0.95, 0.97, 0.97]; // ~ var(--text)
const DARK_DRAW_OPTIONS = {
  backgroundColour: [0, 0, 0, 0], // transparent
  symbolColour: [0.95, 0.97, 0.97, 1],
  legendColour: [0.55, 0.6, 0.65, 1],
  annotationColour: [0.55, 0.6, 0.65, 1],
  bondLineWidth: 1.1,
  atomColourPalette: {
    "-1": LIGHT, // default / fallback
    "0": LIGHT,
    "1": LIGHT, // H
    "6": LIGHT, // C  -> light bonds
    "7": [0.42, 0.64, 1.0], // N
    "8": [1.0, 0.45, 0.45], // O
    "9": [0.35, 0.85, 0.5], // F
    "15": [1.0, 0.6, 0.3], // P
    "16": [0.95, 0.8, 0.25], // S
    "17": [0.35, 0.85, 0.5], // Cl
    "35": [0.8, 0.5, 0.35], // Br
    "53": [0.7, 0.5, 0.95], // I
  },
};

/**
 * Render a 2D depiction of a SMILES string with RDKit-JS, drawn for dark mode
 * (light bonds on a transparent background — see DARK_DRAW_OPTIONS). Invalid structures
 * (shouldn't happen for firewalled candidates, but might for free-typed input) degrade
 * to a small placeholder rather than throwing.
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

  const svg = useMemo(() => {
    if (!rdkit) return null;
    const mol = rdkit.get_mol(smiles);
    if (!mol) return null;
    try {
      if (!mol.is_valid()) return null;
      return mol.get_svg_with_highlights(JSON.stringify({ width, height, ...DARK_DRAW_OPTIONS }));
    } finally {
      mol.delete(); // free the WASM-side molecule
    }
  }, [rdkit, smiles, width, height]);

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
      className="molstruct"
      style={{ height }}
      // RDKit-generated SVG; the input is a SMILES string, output is sanitized vector markup.
      dangerouslySetInnerHTML={{ __html: svg }}
    />
  );
}
