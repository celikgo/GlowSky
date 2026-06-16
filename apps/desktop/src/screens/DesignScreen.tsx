import { useEffect, useRef, useState } from "react";
import {
  api,
  type Candidate,
  type DesignPlan,
  type TraceEntry,
} from "../lib/api";
import { MoleculeCard } from "./MoleculeCard";

const EXAMPLE = {
  goal: "Make 12 analogs with MW<300, logP 1-3, no PAINS, drug-like",
  seed: "c1ccccc1C(=O)O",
};

/** Reorder streamed cards to the server's final ranking (by InChIKey). */
function rankBy(cards: Candidate[], order: string[]): Candidate[] {
  const idx = new Map(order.map((k, i) => [k, i]));
  return [...cards].sort(
    (a, b) => (idx.get(a.inchikey) ?? Infinity) - (idx.get(b.inchikey) ?? Infinity),
  );
}

export function DesignScreen() {
  const [goal, setGoal] = useState(EXAMPLE.goal);
  const [seed, setSeed] = useState(EXAMPLE.seed);

  const [streaming, setStreaming] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // streamed state, filled milestone by milestone
  const [parent, setParent] = useState<string | null>(null);
  const [plan, setPlan] = useState<DesignPlan | null>(null);
  const [candidates, setCandidates] = useState<Candidate[]>([]);
  const [trace, setTrace] = useState<TraceEntry[]>([]);
  const [explanation, setExplanation] = useState<string | null>(null);
  const [runId, setRunId] = useState<string | null>(null);
  const [models, setModels] = useState<Record<string, string>>({});

  const cancelRef = useRef<(() => void) | null>(null);
  // Close any live socket when the screen unmounts.
  useEffect(() => () => cancelRef.current?.(), []);

  function run() {
    cancelRef.current?.(); // drop any in-flight run
    setError(null);
    setParent(null);
    setPlan(null);
    setCandidates([]);
    setTrace([]);
    setExplanation(null);
    setRunId(null);
    setModels({});
    setStreaming(true);

    cancelRef.current = api.streamDesign(goal.trim(), seed.trim(), {
      onPlan: (p, pl) => {
        setParent(p);
        setPlan(pl);
      },
      onCandidate: (c) => setCandidates((cs) => [...cs, c]),
      onTrace: (t) => setTrace((ts) => [...ts, t]),
      onRanked: (order) => setCandidates((cs) => rankBy(cs, order)),
      onExplanation: (t) => setExplanation(t),
      onComplete: (r) => {
        setCandidates(r.candidates); // authoritative final set + order
        setTrace(r.trace);
        setRunId(r.run_id);
        setModels(r.models_used);
        if (r.explanation) setExplanation(r.explanation);
        setStreaming(false);
      },
      onError: (m) => {
        setError(m);
        setStreaming(false);
      },
    });
  }

  const kept = candidates.filter((c) => c.passed_filters).length;
  const hasResult = streaming || candidates.length > 0 || plan !== null || runId !== null;

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
          <button
            className="btn"
            onClick={run}
            disabled={streaming || !goal.trim() || !seed.trim()}
          >
            {streaming ? <span className="spinner" /> : "✦"}
            {streaming ? "Designing…" : "Run design"}
          </button>
        </div>
        {error ? <div className="design__error">{error}</div> : null}
      </section>

      {hasResult ? (
        <>
          {/* Summary + plan — updates live as candidates stream in */}
          <div className="section-title">
            Result{streaming ? <span className="spinner spinner--inline" /> : null}
          </div>
          <div className="summary">
            <span className="chip chip--accent">
              {candidates.length} generated · {kept} passed
            </span>
            {parent ? <span className="chip">parent {parent}</span> : null}
            {Object.entries(models).map(([k, v]) => (
              <span className="chip" key={k}>
                {k}: {v}
              </span>
            ))}
            {runId ? (
              <span className="export-links">
                <a className="chip" href={api.exportRunUrl(runId, "ipynb")} target="_blank" rel="noreferrer">
                  ⬇ notebook
                </a>
                <a className="chip" href={api.exportRunUrl(runId, "md")} target="_blank" rel="noreferrer">
                  ⬇ report
                </a>
              </span>
            ) : null}
          </div>

          {/* Candidates — each card appears the moment it's profiled */}
          <div className="section-title">Candidates</div>
          <div className="grid">
            {candidates.map((c) => (
              <MoleculeCard key={c.inchikey + c.modification} candidate={c} />
            ))}
            {streaming && candidates.length === 0 ? (
              <div className="explanation card">Planning and generating analogs…</div>
            ) : null}
          </div>

          {/* Explanation */}
          {explanation ? (
            <>
              <div className="section-title">Agent explanation</div>
              <div className="explanation card">{explanation}</div>
            </>
          ) : null}

          {/* Trace */}
          {trace.length > 0 ? (
            <>
              <div className="section-title">Execution trace</div>
              <div className="trace card">
                {trace.map((t) => (
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
        </>
      ) : null}
    </div>
  );
}
