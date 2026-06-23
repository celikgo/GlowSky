/**
 * The medicinal-chemistry deep-dive for one molecule — surfaces the expert chemistry that was
 * previously backend-only: the **MPO desirability** breakdown (per-property + the limiting axis),
 * the full **drug-likeness rule battery**, a **synthesizability** verdict with a one-step route,
 * and **structural alerts**. Opened from any molecule card via `useInspector`.
 *
 * The 2D structure renders client-side (RDKit-JS) so it shows immediately; the assessment is
 * fetched from `/molecules/assess`. If the backend isn't up, the structure + a clear hint still
 * render — the panel degrades gracefully rather than going blank.
 */
import { createContext, useContext, useEffect, useState } from "react"
import { api, ApiError, type Assessment } from "../lib/api"
import { MoleculeDepiction } from "./MoleculeDepiction"

export interface InspectTarget {
  smiles: string
  name?: string | null
}

export const InspectContext = createContext<{ inspect: (t: InspectTarget) => void }>({
  inspect: () => {},
})

export function useInspector() {
  return useContext(InspectContext)
}

const SA_VARIANT: Record<string, string> = {
  easy: "chip--success",
  moderate: "chip--accent",
  hard: "chip--danger",
}

export function MoleculeInspector({
  target,
  onClose,
}: {
  target: InspectTarget | null
  onClose: () => void
}) {
  const [data, setData] = useState<Assessment | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    if (!target) return
    setData(null)
    setError(null)
    setLoading(true)
    let live = true
    api
      .assess(target.smiles)
      .then((a) => live && setData(a))
      .catch((e) =>
        live &&
        setError(
          e instanceof ApiError && e.status === 401
            ? "Sign in (paste a token in Settings) to load the assessment."
            : "Could not reach the backend. Is `make run` up?",
        ),
      )
      .finally(() => live && setLoading(false))
    return () => {
      live = false
    }
  }, [target])

  if (!target) return null

  return (
    <div className="editor-overlay" onClick={onClose}>
      <div className="inspector" onClick={(e) => e.stopPropagation()}>
        <div className="editor-modal__head">
          <span className="editor-modal__title">{target.name || "Molecule"}</span>
          <button className="editor-modal__close" onClick={onClose} aria-label="Close">
            ✕
          </button>
        </div>

        <div className="inspector__body">
          <div className="inspector__structure">
            <MoleculeDepiction smiles={target.smiles} width={300} height={200} />
            <div className="mono inspector__smiles">{target.smiles}</div>
          </div>

          <div className="inspector__panels">
            {loading ? (
              <div className="inspector__state">
                <span className="spinner" /> Assessing…
              </div>
            ) : error ? (
              <div className="inspector__state inspector__state--error">{error}</div>
            ) : data ? (
              <>
                <MpoSection data={data} />
                <SynthSection data={data} />
                <RulesSection data={data} />
                <AlertsSection data={data} />
              </>
            ) : null}
          </div>
        </div>
      </div>
    </div>
  )
}

function MpoSection({ data }: { data: Assessment }) {
  const { score, profile, desirability, limiting } = data.mpo
  const entries = Object.entries(desirability)
  return (
    <section className="inspector__section">
      <div className="inspector__sectionhead">
        <span className="inspector__sectiontitle">MPO desirability</span>
        <span className="chip chip--accent">
          {score.toFixed(2)} · {profile}
        </span>
      </div>
      <div className="inspector__bars">
        {entries.map(([prop, d]) => (
          <div className="inspector__bar" key={prop}>
            <span className={`inspector__barlabel ${prop === limiting ? "is-limiting" : ""}`}>
              {prop.replace(/_/g, " ")}
            </span>
            <span className="inspector__bartrack">
              <span
                className={`inspector__barfill ${prop === limiting ? "is-limiting" : ""}`}
                style={{ width: `${Math.round(d * 100)}%` }}
              />
            </span>
            <span className="inspector__barval">{d.toFixed(2)}</span>
          </div>
        ))}
      </div>
      {limiting ? (
        <div className="inspector__note">
          Limiting property: <strong>{limiting.replace(/_/g, " ")}</strong> — the axis to fix first.
        </div>
      ) : null}
    </section>
  )
}

function SynthSection({ data }: { data: Assessment }) {
  const s = data.synthesizability
  return (
    <section className="inspector__section">
      <div className="inspector__sectionhead">
        <span className="inspector__sectiontitle">Synthesizability</span>
        <span className={`chip ${SA_VARIANT[s.sa_label] ?? ""}`}>
          SA {s.sa_score} · {s.sa_label}
        </span>
      </div>
      <div className="inspector__note">{s.assessment}</div>
      {s.best_disconnection ? (
        <div className="inspector__route">
          <span className="chip chip--accent">{s.best_disconnection.reaction}</span>
          <span className="inspector__arrow">⇒</span>
          {s.best_disconnection.precursors.map((p, i) => (
            <span key={`${p}-${i}`} className="chip mono">
              {p}
            </span>
          ))}
          {s.best_disconnection.all_building_blocks ? (
            <span className="chip chip--success" title="heuristic: small + easy-to-make">
              building blocks
            </span>
          ) : null}
        </div>
      ) : null}
    </section>
  )
}

function RulesSection({ data }: { data: Assessment }) {
  const rules = data.rules.rules
  return (
    <section className="inspector__section">
      <div className="inspector__sectionhead">
        <span className="inspector__sectiontitle">Drug-likeness rules</span>
        <span className="chip">{data.rules.n_passed}/7 passed</span>
      </div>
      <div className="inspector__rules">
        {Object.entries(rules).map(([name, r]) => (
          <span
            key={name}
            className={`chip ${r.pass ? "chip--success" : "chip--danger"}`}
            title={r.violations.join("; ") || "passes"}
          >
            {name.replace(/_/g, " ")}
          </span>
        ))}
      </div>
    </section>
  )
}

function AlertsSection({ data }: { data: Assessment }) {
  const { has_pains, has_brenk, pains, brenk } = data.alerts
  return (
    <section className="inspector__section">
      <div className="inspector__sectionhead">
        <span className="inspector__sectiontitle">Structural alerts</span>
      </div>
      <div className="inspector__rules">
        <span className={`chip ${has_pains ? "chip--danger" : "chip--success"}`} title={pains.join("; ")}>
          PAINS {has_pains ? `(${pains.length})` : "clean"}
        </span>
        <span className={`chip ${has_brenk ? "chip--danger" : "chip--success"}`} title={brenk.join("; ")}>
          BRENK {has_brenk ? `(${brenk.length})` : "clean"}
        </span>
      </div>
    </section>
  )
}
