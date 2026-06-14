import { useMemo } from "react";
import { useRDKit } from "../hooks/useRDKit";

/**
 * Render a 2D depiction of a SMILES string with RDKit-JS.
 *
 * RDKit draws on a white background, so the structure sits on a light "paper" tile —
 * readable on the Dim card and a familiar look for chemists. Invalid structures (which
 * shouldn't happen for firewalled candidates, but might for free-typed input) degrade
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
      return mol.is_valid() ? mol.get_svg(width, height) : null;
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
