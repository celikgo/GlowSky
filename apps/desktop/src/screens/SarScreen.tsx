import { useState } from "react";
import { api, ApiError, type MatchedPairsResult, type SarTransformsResult } from "../lib/api";

// Descriptor keys the backend can measure a pair's Δ on, plus the MPO desirability.
const PROPERTIES = [
  "logp",
  "mw",
  "tpsa",
  "hbd",
  "hba",
  "rotatable_bonds",
  "aromatic_rings",
  "fsp3",
  "qed",
  "heavy_atoms",
  "mpo",
] as const;

// A small congeneric benzoic-acid series — shared scaffold, single-substituent swaps → matched pairs.
const EXAMPLE = [
  "c1ccccc1C(=O)O",
  "Fc1ccccc1C(=O)O",
  "Cc1ccccc1C(=O)O",
  "Clc1ccccc1C(=O)O",
  "Oc1ccccc1C(=O)O",
].join("\n");

/** Signed, fixed-precision delta for the tables (e.g. +0.42 / -0.40). */
function fmt(n: number): string {
  return `${n > 0 ? "+" : ""}${n.toFixed(2)}`;
}

/**
 * Matched-pairs & SAR screen — a dedicated view over the `matched_pairs` and `sar_transforms`
 * tools. Given a congeneric set and a property, it renders the aggregated SAR transforms (each
 * transformation's mean/median/range effect, ranked by support) and the underlying matched pairs.
 * The mining lives server-side (`services/chemistry/mmp.py`); this surfaces it as readable tables,
 * beyond the generic Tools playground.
 */
export function SarScreen() {
  const [text, setText] = useState(EXAMPLE);
  const [property, setProperty] = useState<string>("logp");
  const [minCount, setMinCount] = useState("1");
  const [running, setRunning] = useState(false);
  const [transforms, setTransforms] = useState<SarTransformsResult | null>(null);
  const [pairs, setPairs] = useState<MatchedPairsResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function run() {
    const list = text
      .split(/\n+/)
      .map((s) => s.trim())
      .filter(Boolean);
    if (list.length < 2) {
      setError("Enter at least two molecules (one SMILES per line) to find matched pairs.");
      return;
    }
    setRunning(true);
    setError(null);
    setTransforms(null);
    setPairs(null);
    const mc = parseInt(minCount, 10);
    try {
      const [sar, mmp] = await Promise.all([
        api.runTool("sar_transforms", {
          smiles_list: list,
          property,
          min_count: Number.isNaN(mc) ? 1 : mc,
        }),
        api.runTool("matched_pairs", { smiles_list: list, property }),
      ]);
      setTransforms(sar.output as SarTransformsResult);
      setPairs(mmp.output as MatchedPairsResult);
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
    <div className="analysis sar">
      <section className="analysis__form card">
        <div className="section-title">Matched pairs &amp; SAR</div>
        <p className="analysis__hint">
          Mine matched molecular pairs from a congeneric set and aggregate each single-group
          transformation&rsquo;s effect on a property — the basis of rational optimisation (e.g.{" "}
          <span className="mono">&ldquo;H→F lowers logP by 0.4 on average (n=6)&rdquo;</span>).
          Deterministic and RDKit-computed (Hussain–Rea single-cut fragmentation); no LLM.
        </p>
        <div className="field">
          <label className="field__label">Molecule set (one SMILES per line)</label>
          <textarea
            className="textarea mono"
            value={text}
            onChange={(e) => setText(e.target.value)}
            rows={6}
          />
        </div>
        <div className="analysis__inputrow">
          <div className="formfield">
            <label className="field__label">property</label>
            <select
              className="input mono"
              value={property}
              onChange={(e) => setProperty(e.target.value)}
            >
              {PROPERTIES.map((p) => (
                <option key={p} value={p}>
                  {p}
                </option>
              ))}
            </select>
          </div>
          <div className="formfield analysis__num">
            <label className="field__label">min count</label>
            <input
              className="input mono"
              type="number"
              value={minCount}
              onChange={(e) => setMinCount(e.target.value)}
            />
          </div>
          <button className="btn" onClick={run} disabled={running}>
            {running ? <span className="spinner" /> : "⊞"}
            {running ? "Mining…" : "Mine SAR"}
          </button>
        </div>
        {error ? <div className="design__error">{error}</div> : null}
      </section>

      {transforms ? (
        <>
          <div className="section-title">Transforms · {property}</div>
          <div className="summary">
            <span className="chip chip--accent">{transforms.n_molecules} molecules</span>
            <span className="chip">{transforms.n_transforms} transforms</span>
          </div>
          {transforms.n_transforms === 0 ? (
            <div className="explanation card">
              No transforms met the support threshold. Try a larger or more congeneric set, or lower
              the min count.
            </div>
          ) : (
            <table className="datatable">
              <thead>
                <tr>
                  <th>transformation</th>
                  <th>n</th>
                  <th>mean Δ</th>
                  <th>median Δ</th>
                  <th>min</th>
                  <th>max</th>
                </tr>
              </thead>
              <tbody>
                {transforms.transforms.map((t) => (
                  <tr key={t.transformation}>
                    <td className="mono">{t.transformation}</td>
                    <td>{t.n}</td>
                    <td className={t.mean_delta < 0 ? "datatable__neg" : "datatable__pos"}>
                      {fmt(t.mean_delta)}
                    </td>
                    <td>{fmt(t.median_delta)}</td>
                    <td>{fmt(t.min_delta)}</td>
                    <td>{fmt(t.max_delta)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </>
      ) : null}

      {pairs && pairs.n_pairs > 0 ? (
        <>
          <div className="section-title">Matched pairs · {pairs.n_pairs}</div>
          <table className="datatable">
            <thead>
              <tr>
                <th>A</th>
                <th>B</th>
                <th>transformation</th>
                <th>Δ {pairs.property}</th>
              </tr>
            </thead>
            <tbody>
              {pairs.pairs.map((p, i) => (
                <tr key={`${p.a}-${p.b}-${p.transformation}-${i}`}>
                  <td className="mono">{p.a}</td>
                  <td className="mono">{p.b}</td>
                  <td className="mono">{p.transformation}</td>
                  <td
                    className={
                      p.delta !== undefined && p.delta < 0 ? "datatable__neg" : "datatable__pos"
                    }
                  >
                    {p.delta !== undefined ? fmt(p.delta) : "—"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      ) : null}
    </div>
  );
}
