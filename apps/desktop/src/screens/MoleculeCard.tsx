import type { Candidate } from "../lib/api";
import { MoleculeDepiction } from "../components/MoleculeDepiction";
import { usePalette } from "../components/CommandPalette";
import { useInspector } from "../components/MoleculeInspector";

function num(v: number | boolean | undefined): string {
  return typeof v === "number" ? v.toString() : "—";
}

export function MoleculeCard({
  candidate,
  selected,
  onToggleSelect,
}: {
  candidate: Candidate;
  /** When defined, the card shows a selection checkbox (used on the Design screen to
   *  pick analogs to save into a library). Omit on read-only surfaces. */
  selected?: boolean;
  onToggleSelect?: () => void;
}) {
  const p = candidate.properties;
  const selectable = onToggleSelect !== undefined;
  const { openFor } = usePalette();
  const { inspect } = useInspector();
  const name = candidate.modification || "analog";
  return (
    <article className={`molcard card ${selected ? "molcard--selected" : ""}`}>
      <div className="molcard__head">
        {selectable ? (
          <label className="molcard__select">
            <input type="checkbox" checked={!!selected} onChange={onToggleSelect} />
          </label>
        ) : null}
        <span className="molcard__mod">{candidate.modification || "analog"}</span>
        <span className={`chip ${candidate.passed_filters ? "chip--success" : "chip--danger"}`}>
          {candidate.passed_filters ? "passed" : "filtered"}
        </span>
        <button
          className="molcard__cmdk"
          title="Inspect (med-chem deep-dive)"
          onClick={() => inspect({ smiles: candidate.smiles, name })}
        >
          🔬
        </button>
        <button
          className="molcard__cmdk"
          title="Actions (⌘K)"
          onClick={() => openFor({ smiles: candidate.smiles, name })}
        >
          ⌘K
        </button>
      </div>
      <MoleculeDepiction smiles={candidate.smiles} />
      <div className="molcard__smiles mono">{candidate.smiles}</div>
      <div className="molcard__props">
        <span className="chip">MW {num(p.mw)}</span>
        <span className="chip">logP {num(p.logp)}</span>
        <span className="chip">TPSA {num(p.tpsa)}</span>
        <span className="chip">QED {num(p.qed)}</span>
        {p.mpo !== undefined ? (
          <span className="chip chip--accent" title="multi-parameter optimization desirability">
            MPO {num(p.mpo)}
          </span>
        ) : null}
        {p.has_pains ? <span className="chip chip--danger">PAINS</span> : null}
        {p.lipinski_pass ? <span className="chip chip--success">Ro5</span> : null}
      </div>
    </article>
  );
}
