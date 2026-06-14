import { useState } from "react";
import { api, ApiError, type DesignResult } from "../lib/api";
import { MoleculeCard } from "./MoleculeCard";

const EXAMPLE = {
  goal: "Make 12 analogs with MW<300, logP 1-3, no PAINS, drug-like",
  seed: "c1ccccc1C(=O)O",
};

export function DesignScreen() {
  const [goal, setGoal] = useState(EXAMPLE.goal);
  const [seed, setSeed] = useState(EXAMPLE.seed);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<DesignResult | null>(null);

  async function run() {
    setLoading(true);
    setError(null);
    try {
      setResult(await api.design(goal.trim(), seed.trim()));
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not reach the backend. Is `make run` up?");
    } finally {
      setLoading(false);
    }
  }

  const kept = result?.candidates.filter((c) => c.passed_filters).length ?? 0;

  return (
    <div className="design">
      {/* Composer */}
      <section className="design__composer card">
        <div className="field">
          <label className="field__label">Design goal</label>
          <textarea
            className="textarea"
            value={goal}
            onChange={(e) => setGoal(e.target.value)}
            placeholder="Describe what you want to design, in plain language…"
          />
        </div>
        <div className="design__row">
          <div className="field">
            <label className="field__label">Seed molecule (SMILES)</label>
            <input
              className="input mono"
              value={seed}
              onChange={(e) => setSeed(e.target.value)}
              placeholder="e.g. c1ccccc1C(=O)O"
            />
          </div>
          <button className="btn" onClick={run} disabled={loading || !goal.trim() || !seed.trim()}>
            {loading ? <span className="spinner" /> : "✦"}
            {loading ? "Designing…" : "Run design"}
          </button>
        </div>
        {error ? <div className="design__error">{error}</div> : null}
      </section>

      {result ? (
        <>
          {/* Summary + plan */}
          <div className="section-title">Result</div>
          <div className="summary">
            <span className="chip chip--accent">
              {result.candidates.length} generated · {kept} passed
            </span>
            <span className="chip">parent {result.parent_smiles}</span>
            {Object.entries(result.models_used).map(([k, v]) => (
              <span className="chip" key={k}>
                {k}: {v}
              </span>
            ))}
            {result.run_id ? (
              <span className="export-links">
                <a className="chip" href={api.exportRunUrl(result.run_id, "ipynb")} target="_blank" rel="noreferrer">
                  ⬇ notebook
                </a>
                <a className="chip" href={api.exportRunUrl(result.run_id, "md")} target="_blank" rel="noreferrer">
                  ⬇ report
                </a>
              </span>
            ) : null}
          </div>

          {/* Candidates */}
          <div className="section-title">Candidates</div>
          <div className="grid">
            {result.candidates.map((c) => (
              <MoleculeCard key={c.inchikey + c.modification} candidate={c} />
            ))}
          </div>

          {/* Explanation */}
          {result.explanation ? (
            <>
              <div className="section-title">Agent explanation</div>
              <div className="explanation card">{result.explanation}</div>
            </>
          ) : null}

          {/* Trace */}
          <div className="section-title">Execution trace</div>
          <div className="trace card">
            {result.trace.map((t) => (
              <div className="trace__row" key={t.step}>
                <span className="trace__step">{t.step}</span>
                <span>
                  <span className="trace__tool mono">{t.tool}</span>{" "}
                  <span className="trace__summary">{t.summary}</span>
                </span>
                <span className="trace__meta">
                  {t.duration_ms}ms{t.cache_hit ? " · cached" : ""}
                </span>
              </div>
            ))}
          </div>
        </>
      ) : null}
    </div>
  );
}
