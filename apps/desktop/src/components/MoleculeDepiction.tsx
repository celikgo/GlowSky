import { useState } from "react";
import { MoleculeStructure } from "./MoleculeStructure";
import { Molecule3D } from "./Molecule3D";

/**
 * A molecule depiction with a 2D/3D toggle. Defaults to the cheap, instant RDKit-JS 2D
 * drawing; flipping to 3D lazily fetches a conformer and mounts the WebGL viewer, so the
 * heavier path is paid only when the user asks for it.
 */
export function MoleculeDepiction({
  smiles,
  width = 280,
  height = 170,
}: {
  smiles: string;
  width?: number;
  height?: number;
}) {
  const [mode, setMode] = useState<"2d" | "3d">("2d");

  return (
    <div className="moldepict">
      <div className="moldepict__toggle" role="group" aria-label="structure view">
        <button
          type="button"
          className={`moldepict__btn ${mode === "2d" ? "is-active" : ""}`}
          onClick={() => setMode("2d")}
          aria-pressed={mode === "2d"}
        >
          2D
        </button>
        <button
          type="button"
          className={`moldepict__btn ${mode === "3d" ? "is-active" : ""}`}
          onClick={() => setMode("3d")}
          aria-pressed={mode === "3d"}
        >
          3D
        </button>
      </div>
      {mode === "2d" ? (
        <MoleculeStructure smiles={smiles} width={width} height={height} />
      ) : (
        <Molecule3D smiles={smiles} width={width} height={height} />
      )}
    </div>
  );
}
