/**
 * The display rules that make a prediction honest, asserted.
 *
 * These are not cosmetic tests. Each one pins a property that, if it silently
 * regressed, would turn a hedged estimate back into something that reads like a
 * measurement — which is the failure the whole Prediction shape exists to prevent.
 */
import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { PredictionCard, PredictionPanel, isPrediction, type Prediction } from "./PredictionCard";

const publishedQspr: Prediction = {
  value: -1.99,
  unit: "logS (mol/L)",
  uncertainty: {
    basis: "measured-against-benchmark",
    sigma: 1.1,
    interval: [-4.15, 0.16],
    interval_level: 0.95,
    source: "RMSE 1.10 log units, measured against the Delaney set in CI",
  },
  applicability_domain: {
    verdict: "in",
    checks: { mw_100_to_600: true, "clogp_-3_to_7": true },
    explanation: "inside the model's stated domain",
  },
  provenance: {
    model: "ESOL",
    kind: "published-qspr",
    version: "Delaney-2004",
    trained_on: "2874 measured aqueous solubilities",
    citations: [{ reference: "Delaney 2004", doi: "10.1021/ci034243x", url: "https://doi.org/10.1021/ci034243x" }],
  },
};

const heuristic: Prediction = {
  value: "high",
  uncertainty: { basis: "stated-estimate", probability: 0.85, source: "uncalibrated logistic output" },
  applicability_domain: { verdict: "in", checks: {}, explanation: "in" },
  provenance: {
    model: "hERG liability flag",
    kind: "heuristic",
    version: "1.0.0",
    trained_on: "not fitted to measured data",
    citations: [],
    notes: "UNVALIDATED. Directional only.",
  },
  caveat: "NOT a cardiac safety assessment.",
};

const outOfDomain: Prediction = {
  ...publishedQspr,
  value: 2.4,
  applicability_domain: {
    verdict: "out",
    checks: { mw_100_to_600: false, "clogp_-3_to_7": false },
    explanation: "outside the model's domain on 2 axes",
  },
  caveat: "outside the model's applicability domain — not for decision-making",
};

describe("PredictionCard", () => {
  it("shows the uncertainty interval next to the value, not behind a disclosure", () => {
    render(<PredictionCard label="solubility" prediction={publishedQspr} />);
    // The band must be in the document with no interaction at all.
    expect(screen.getByText(/95% CI \[-4.15, 0.16\]/)).toBeInTheDocument();
    expect(screen.getByText(/-1.99/)).toBeInTheDocument();
  });

  it("states the basis for the error bar", () => {
    render(<PredictionCard label="solubility" prediction={publishedQspr} />);
    expect(screen.getByText(/measured against the Delaney set in CI/)).toBeInTheDocument();
  });

  it("labels a heuristic as unvalidated rather than letting it pass as a model", () => {
    render(<PredictionCard label="herg" prediction={heuristic} />);
    expect(screen.getByText(/HEURISTIC — unvalidated/)).toBeInTheDocument();
  });

  it("does not present a heuristic with the same styling as a published model", () => {
    const { container: h } = render(<PredictionCard label="herg" prediction={heuristic} />);
    const { container: q } = render(<PredictionCard label="sol" prediction={publishedQspr} />);
    expect(h.querySelector(".prediction--heuristic")).not.toBeNull();
    expect(q.querySelector(".prediction--heuristic")).toBeNull();
  });

  it("surfaces a caveat that refuses a safety reading", () => {
    render(<PredictionCard label="herg" prediction={heuristic} />);
    expect(screen.getByText(/NOT a cardiac safety assessment/)).toBeInTheDocument();
  });

  it("marks an out-of-domain value as unusable and shows which checks failed", () => {
    const { container } = render(<PredictionCard label="solubility" prediction={outOfDomain} />);
    expect(screen.getByText("OUT OF DOMAIN")).toBeInTheDocument();
    expect(screen.getByText(/not for decision-making/)).toBeInTheDocument();
    // The hard variant, not the ordinary caution styling.
    expect(container.querySelector(".prediction__caveat--hard")).not.toBeNull();
    // And the individual failing criteria are named, so the verdict is actionable.
    expect(screen.getByText(/mw_100_to_600/)).toBeInTheDocument();
  });

  it("links the citation so a reader can check the source", () => {
    render(<PredictionCard label="solubility" prediction={publishedQspr} />);
    const link = screen.getByRole("link", { name: "10.1021/ci034243x" });
    expect(link).toHaveAttribute("href", "https://doi.org/10.1021/ci034243x");
  });

  it("renders a categorical endpoint's probability rather than dropping it", () => {
    render(<PredictionCard label="herg" prediction={heuristic} />);
    expect(screen.getByText(/p = 0.85/)).toBeInTheDocument();
  });
});

describe("PredictionPanel", () => {
  it("finds predictions nested inside a tool payload", () => {
    const payload = { backend: "rdkit-qspr", predictions: { solubility: publishedQspr, herg: heuristic } };
    render(<PredictionPanel output={payload} />);
    expect(screen.getByText(/95% CI/)).toBeInTheDocument();
    expect(screen.getByText(/HEURISTIC — unvalidated/)).toBeInTheDocument();
  });

  it("renders nothing for a payload with no predictions, so the caller can fall back", () => {
    const { container } = render(<PredictionPanel output={{ mw: 180.16, logp: 1.31 }} />);
    expect(container.firstChild).toBeNull();
  });

  it("does not mistake an arbitrary object for a prediction", () => {
    expect(isPrediction({ value: 1 })).toBe(false);
    expect(isPrediction(publishedQspr)).toBe(true);
  });
});

/**
 * A docking run reports the full range across the poses it found, tagged
 * interval_level = 1.0. That is an observed spread, not a confidence interval: rendering
 * it as "100% CI" would claim total certainty about a number whose whole point is that
 * the search disagreed with itself.
 */
const dockingRange: Prediction = {
  value: -9.1,
  unit: "kcal/mol",
  uncertainty: {
    basis: "ensemble-spread",
    sigma: 0.75,
    interval: [-9.1, -7.6],
    interval_level: 1.0,
    source: "spread across the poses returned by this run, NOT the error of the scoring function",
  },
  applicability_domain: { verdict: "in", checks: {}, explanation: "in" },
  provenance: {
    model: "autodock-vina",
    kind: "physics-engine",
    version: "1.2.5",
    trained_on: "empirical scoring function fitted to crystallographic complexes",
    citations: [{ reference: "Trott & Olson 2010", doi: "10.1002/jcc.21334", url: "https://doi.org/10.1002/jcc.21334" }],
  },
  caveat: "docking score, not a binding affinity — a ranking quantity for this receptor",
};

describe("a full observed range is not a confidence interval", () => {
  it("labels an interval_level of 1.0 as a range, never as a 100% CI", () => {
    render(<PredictionCard label="dock" prediction={dockingRange} />);
    expect(screen.getByText(/range \[-9\.1, -7\.6\]/)).toBeTruthy();
    expect(screen.queryByText(/100% CI/)).toBeNull();
  });

  it("still renders a genuine 95% CI as a CI", () => {
    render(<PredictionCard label="solubility" prediction={publishedQspr} />);
    expect(screen.getByText(/95% CI/)).toBeTruthy();
  });

  it("shows a docking score with its 'not a binding affinity' caveat", () => {
    render(<PredictionCard label="dock" prediction={dockingRange} />);
    expect(screen.getByText(/not a binding affinity/)).toBeTruthy();
  });
});

describe("a published heuristic is labelled as ranking, not measuring", () => {
  it("names the published-heuristic kind rather than falling through to the raw string", () => {
    const sa: Prediction = {
      ...dockingRange,
      value: 1.58,
      unit: "SA score (1 easy – 10 hard)",
      uncertainty: { basis: "stated-estimate", sigma: 1.0, source: "stated resolution" },
      provenance: { ...dockingRange.provenance, kind: "published-heuristic", model: "Ertl & Schuffenhauer SA score" },
      caveat: undefined,
    };
    render(<PredictionCard label="sa_score" prediction={sa} />);
    expect(screen.getByText(/ranks, does not measure/)).toBeTruthy();
  });
});
