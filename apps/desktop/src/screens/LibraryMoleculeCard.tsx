import type { LibraryMolecule } from "../lib/api";
import { MoleculeDepiction } from "../components/MoleculeDepiction";
import { usePalette } from "../components/CommandPalette";
import { useInspector } from "../components/MoleculeInspector";

function fmt(v: number | boolean | string | undefined): string | null {
  if (v === undefined || v === null || v === "") return null;
  return typeof v === "number" ? String(v) : String(v);
}

// Property keys we promote to chips if present (numeric profile or imported columns).
const PROMOTED = ["mw", "logp", "tpsa", "qed"];

export function LibraryMoleculeCard({ mol }: { mol: LibraryMolecule }) {
  const p = mol.properties || {};
  const promoted = PROMOTED.filter((k) => k in p);
  // Up to a few imported (non-profile) columns, so CSV data is visible.
  const extras = Object.keys(p)
    .filter((k) => !PROMOTED.includes(k))
    .slice(0, 3);

  const { openFor } = usePalette();
  const { inspect } = useInspector();
  return (
    <article className="molcard card">
      <div className="molcard__head">
        <span className="molcard__mod">{mol.name || "untitled"}</span>
        <span className="chip">{mol.source}</span>
        <button
          className="molcard__cmdk"
          title="Inspect (med-chem deep-dive)"
          onClick={() => inspect({ smiles: mol.canonical_smiles, name: mol.name })}
        >
          🔬
        </button>
        <button
          className="molcard__cmdk"
          title="Actions (⌘K)"
          onClick={() => openFor({ smiles: mol.canonical_smiles, name: mol.name })}
        >
          ⌘K
        </button>
      </div>
      <MoleculeDepiction smiles={mol.canonical_smiles} />
      <div className="molcard__smiles mono">{mol.canonical_smiles}</div>
      {promoted.length || extras.length ? (
        <div className="molcard__props">
          {promoted.map((k) => (
            <span className="chip" key={k}>
              {k} {fmt(p[k])}
            </span>
          ))}
          {extras.map((k) => (
            <span className="chip chip--accent" key={k} title="imported column">
              {k}: {fmt(p[k])}
            </span>
          ))}
        </div>
      ) : null}
    </article>
  );
}
