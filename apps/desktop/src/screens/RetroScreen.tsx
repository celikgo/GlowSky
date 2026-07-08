import { useState } from "react";
import { api, ApiError, type RetrosynthesisResult } from "../lib/api";
import { MoleculeStructure } from "../components/MoleculeStructure";

// Paracetamol — a clean one-step amide-coupling disconnection into building-block precursors.
const EXAMPLE = "CC(=O)Nc1ccc(O)cc1";

/**
 * Retrosynthesis screen — a dedicated view over the `retrosynthesize` tool. Renders each one-step
 * disconnection as a route: the target on the left, an arrow, and its validated precursors on the
 * right (2D depictions), with a badge for routes whose precursors all look like purchasable
 * building blocks. The compute lives server-side (`services/chemistry/retrosynthesis.py`); this is
 * the meaningful visualisation of its result, beyond the generic Tools playground.
 */
export function RetroScreen() {
  const [smiles, setSmiles] = useState(EXAMPLE);
  const [maxRoutes, setMaxRoutes] = useState("10");
  const [running, setRunning] = useState(false);
  const [result, setResult] = useState<RetrosynthesisResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function run() {
    const target = smiles.trim();
    if (!target) return;
    setRunning(true);
    setError(null);
    setResult(null);
    const args: Record<string, unknown> = { canonical_smiles: target };
    const n = parseInt(maxRoutes, 10);
    if (!Number.isNaN(n)) args.max_routes = n;
    try {
      const res = await api.runTool("retrosynthesize", args);
      setResult(res.output as RetrosynthesisResult);
    } catch (e) {
      setError(
        e instanceof ApiError
          ? `${e.status}: ${e.message}`
          : "Could not reach the backend. Is `make run` up?",
      );
    } finally {
      setRunning(false);
    }
  }

  return (
    <div className="analysis retro">
      <section className="analysis__form card">
        <div className="section-title">Retrosynthesis</div>
        <p className="analysis__hint">
          One-step retrosynthetic disconnections via named reactions (amide coupling, Suzuki,
          esterification, reductive amination, …). Each route breaks the target at a recognised bond
          into validated precursors; routes whose precursors all look like purchasable building
          blocks are surfaced first. Template-based and deterministic — an honest heuristic, not an
          ML route planner.
        </p>
        <div className="analysis__inputrow">
          <div className="field">
            <label className="field__label">Target molecule (SMILES)</label>
            <input
              className="input mono"
              value={smiles}
              onChange={(e) => setSmiles(e.target.value)}
              placeholder="e.g. CC(=O)Nc1ccc(O)cc1"
            />
          </div>
          <div className="formfield analysis__num">
            <label className="field__label">max routes</label>
            <input
              className="input mono"
              type="number"
              value={maxRoutes}
              onChange={(e) => setMaxRoutes(e.target.value)}
            />
          </div>
          <button className="btn" onClick={run} disabled={running || !smiles.trim()}>
            {running ? <span className="spinner" /> : "⇋"}
            {running ? "Analyzing…" : "Disconnect"}
          </button>
        </div>
        {error ? <div className="design__error">{error}</div> : null}
      </section>

      {result ? (
        <>
          <div className="section-title">
            {result.n_disconnections} route{result.n_disconnections === 1 ? "" : "s"}
          </div>
          {result.n_disconnections === 0 ? (
            <div className="explanation card">
              No recognised one-step disconnection for this target — it needs route design beyond
              these templates.
            </div>
          ) : (
            <div className="retro__routes">
              {result.disconnections.map((d, i) => (
                <div className="retro__route card" key={`${d.reaction}-${i}`}>
                  <div className="retro__routehead">
                    <span className="chip chip--accent">{d.reaction}</span>
                    {d.all_building_blocks ? (
                      <span className="chip chip--success">building blocks</span>
                    ) : (
                      <span className="chip">multi-step precursors</span>
                    )}
                    <span className="retro__routen mono">
                      {d.precursors.length} precursor{d.precursors.length === 1 ? "" : "s"}
                    </span>
                  </div>
                  <div className="retro__tree">
                    <div className="retro__node">
                      <MoleculeStructure smiles={result.target} width={200} height={150} />
                      <div className="retro__smiles mono">{result.target}</div>
                    </div>
                    <div className="retro__arrow" aria-hidden="true">
                      ⇒
                    </div>
                    <div className="retro__precursors">
                      {d.precursors.map((p, j) => (
                        <div className="retro__node" key={`${p}-${j}`}>
                          <MoleculeStructure smiles={p} width={180} height={130} />
                          <div className="retro__smiles mono">{p}</div>
                        </div>
                      ))}
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </>
      ) : null}
    </div>
  );
}
