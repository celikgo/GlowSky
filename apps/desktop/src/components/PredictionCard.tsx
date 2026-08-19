/**
 * Renders a prediction the way a prediction should be read.
 *
 * The backend returns every predicted value together with its uncertainty, its
 * applicability domain and its provenance (services/chemistry/provenance.py). Before
 * this component, the Tools screen printed that payload as raw JSON — technically
 * present, practically invisible, and a value skimmed out of a JSON blob is read
 * exactly like a measurement, which is the failure the payload shape exists to prevent.
 *
 * So the display puts them in the order a chemist needs them:
 *   1. Is this molecule even in scope?  (domain badge, first, and loud when it is not)
 *   2. How wrong might this be?          (the interval, next to the value, never hidden)
 *   3. Who says so?                      (model, kind, and a citation that resolves)
 *
 * A HEURISTIC is styled differently from a published QSPR on purpose. Rendering seven
 * ADMET endpoints in one uniform panel is precisely how an in-house correlation ends up
 * being quoted like a measurement.
 */
import type { JSX } from "react";

export type DomainVerdict = "in" | "borderline" | "out" | "unknown";

export interface Uncertainty {
  basis: string;
  sigma?: number;
  interval?: [number, number];
  interval_level?: number;
  probability?: number;
  source?: string;
}

export interface Citation {
  reference: string;
  doi?: string;
  url?: string;
}

export interface Provenance {
  model: string;
  kind: string;
  version: string;
  trained_on: string;
  citations: Citation[];
  notes?: string;
}

export interface ApplicabilityDomain {
  verdict: DomainVerdict;
  checks: Record<string, boolean>;
  explanation: string;
}

export interface Prediction {
  value: number | string | boolean | null;
  unit?: string;
  uncertainty: Uncertainty;
  applicability_domain: ApplicabilityDomain;
  provenance: Provenance;
  caveat?: string;
  [extra: string]: unknown;
}

/** Duck-type a Prediction. The Tools screen renders arbitrary tool output. */
export function isPrediction(value: unknown): value is Prediction {
  if (typeof value !== "object" || value === null) return false;
  const v = value as Record<string, unknown>;
  return (
    "value" in v &&
    typeof v.uncertainty === "object" &&
    v.uncertainty !== null &&
    typeof v.applicability_domain === "object" &&
    v.applicability_domain !== null &&
    typeof v.provenance === "object" &&
    v.provenance !== null
  );
}

const DOMAIN_LABEL: Record<DomainVerdict, string> = {
  in: "in domain",
  borderline: "borderline",
  out: "OUT OF DOMAIN",
  unknown: "domain undefined",
};

/** `out` is danger, not a neutral note: the value must not be used. */
const DOMAIN_CHIP: Record<DomainVerdict, string> = {
  in: "chip--success",
  borderline: "chip--warn",
  out: "chip--danger",
  unknown: "",
};

/** A heuristic must not borrow the visual authority of a published model. */
const KIND_LABEL: Record<string, string> = {
  "published-qspr": "published QSPR",
  "published-rule": "published rule",
  "substructure-alert": "substructure alert",
  "physics-engine": "physics engine",
  "published-heuristic": "published heuristic — ranks, does not measure",
  heuristic: "HEURISTIC — unvalidated",
  "deterministic-descriptor": "exact",
};

function formatValue(p: Prediction): string {
  if (p.value === null) return "—";
  if (typeof p.value === "boolean") return p.value ? "yes" : "no";
  if (typeof p.value === "number") return String(p.value);
  return p.value;
}

/**
 * The interval, or the probability for a categorical endpoint.
 * Returns null only when the value is genuinely exact — never merely because a band
 * is inconvenient to render.
 */
function formatSpread(u: Uncertainty): string | null {
  if (u.interval) {
    const level = u.interval_level ?? 0.95;
    // level 1.0 is a full observed range (e.g. the min/max across docking poses), not a
    // confidence interval. Rendering it as "100% CI" would claim total certainty —
    // the exact inversion of what the field means.
    if (level >= 1) return `range [${u.interval[0]}, ${u.interval[1]}]`;
    return `${Math.round(level * 100)}% CI [${u.interval[0]}, ${u.interval[1]}]`;
  }
  if (typeof u.probability === "number") return `p = ${u.probability}`;
  if (typeof u.sigma === "number") return `σ = ${u.sigma}`;
  return null;
}

export function PredictionCard({
  label,
  prediction,
}: {
  label: string;
  prediction: Prediction;
}): JSX.Element {
  const { uncertainty, applicability_domain: domain, provenance } = prediction;
  const spread = formatSpread(uncertainty);
  const isHeuristic = provenance.kind === "heuristic";
  const outOfDomain = domain.verdict === "out";

  return (
    <div className={`prediction ${isHeuristic ? "prediction--heuristic" : ""}`}>
      <div className="prediction__head">
        <span className="prediction__label">{label}</span>
        <span className={`chip ${DOMAIN_CHIP[domain.verdict] ?? ""}`}>
          {DOMAIN_LABEL[domain.verdict] ?? domain.verdict}
        </span>
        <span className={`chip ${isHeuristic ? "chip--warn" : ""}`}>
          {KIND_LABEL[provenance.kind] ?? provenance.kind}
        </span>
      </div>

      <div className="prediction__value mono">
        {formatValue(prediction)}
        {prediction.unit ? <span className="prediction__unit"> {prediction.unit}</span> : null}
        {/* The band sits beside the value, never in a tooltip or a details pane. A
            number whose uncertainty takes a click to see is a number read without it. */}
        {spread ? <span className="prediction__spread">{spread}</span> : null}
      </div>

      {uncertainty.source ? (
        <div className="prediction__note">{uncertainty.source}</div>
      ) : null}

      {/* An out-of-domain value is shown — hiding it would hide that the model has an
          opinion — but it is shown as unusable. */}
      {outOfDomain || prediction.caveat ? (
        <div className={`prediction__caveat ${outOfDomain ? "prediction__caveat--hard" : ""}`}>
          {prediction.caveat ?? domain.explanation}
        </div>
      ) : null}

      {domain.verdict !== "in" && Object.keys(domain.checks).length ? (
        <div className="prediction__checks">
          {Object.entries(domain.checks).map(([name, ok]) => (
            <span key={name} className={`chip ${ok ? "" : "chip--danger"}`}>
              {ok ? "✓" : "✗"} {name}
            </span>
          ))}
        </div>
      ) : null}

      <div className="prediction__prov">
        <span className="prediction__model">{provenance.model}</span>
        <span className="prediction__trained">{provenance.trained_on}</span>
        {provenance.citations.map((c) =>
          c.url ? (
            <a
              key={c.url}
              className="prediction__cite"
              href={c.url}
              target="_blank"
              rel="noreferrer"
            >
              {c.doi ?? "source"}
            </a>
          ) : null,
        )}
      </div>

      {provenance.notes ? <div className="prediction__note">{provenance.notes}</div> : null}
    </div>
  );
}

/**
 * Find the predictions inside an arbitrary tool payload and render them.
 *
 * Returns null when there are none, so the caller falls back to raw JSON rather than
 * showing an empty panel.
 */
export function PredictionPanel({ output }: { output: unknown }): JSX.Element | null {
  const found: Array<[string, Prediction]> = [];

  const walk = (node: unknown, path: string) => {
    if (isPrediction(node)) {
      found.push([path || "prediction", node]);
      return;
    }
    if (Array.isArray(node)) {
      node.forEach((v, i) => walk(v, `${path}[${i}]`));
    } else if (typeof node === "object" && node !== null) {
      for (const [k, v] of Object.entries(node as Record<string, unknown>)) {
        walk(v, path ? `${path}.${k}` : k);
      }
    }
  };
  walk(output, "");

  if (!found.length) return null;
  return (
    <div className="predictions">
      {found.map(([label, p]) => (
        <PredictionCard key={label} label={label} prediction={p} />
      ))}
    </div>
  );
}
