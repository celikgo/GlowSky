import type { Candidate } from "../lib/api";

function num(v: number | boolean | undefined): string {
  return typeof v === "number" ? v.toString() : "—";
}

export function MoleculeCard({ candidate }: { candidate: Candidate }) {
  const p = candidate.properties;
  return (
    <article className="molcard card">
      <div className="molcard__head">
        <span className="molcard__mod">{candidate.modification || "analog"}</span>
        <span className={`chip ${candidate.passed_filters ? "chip--success" : "chip--danger"}`}>
          {candidate.passed_filters ? "passed" : "filtered"}
        </span>
      </div>
      <div className="molcard__smiles mono">{candidate.smiles}</div>
      <div className="molcard__props">
        <span className="chip">MW {num(p.mw)}</span>
        <span className="chip">logP {num(p.logp)}</span>
        <span className="chip">TPSA {num(p.tpsa)}</span>
        <span className="chip chip--accent">QED {num(p.qed)}</span>
        {p.has_pains ? <span className="chip chip--danger">PAINS</span> : null}
        {p.lipinski_pass ? <span className="chip chip--success">Ro5</span> : null}
      </div>
    </article>
  );
}
