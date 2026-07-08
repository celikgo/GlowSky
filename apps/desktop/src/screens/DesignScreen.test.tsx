import { describe, expect, it, vi } from "vitest";
import { act, fireEvent, render, screen } from "@testing-library/react";
import type { Candidate, DesignStreamHandlers } from "../lib/api";
import { DesignScreen } from "./DesignScreen";

const { streamDesign } = vi.hoisted(() => ({ streamDesign: vi.fn() }));

vi.mock("../lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../lib/api")>();
  return { ...actual, api: { ...actual.api, streamDesign } };
});

// Isolate the stream-state reducer from the heavy children (RDKit card, Ketcher editor modal).
vi.mock("./MoleculeCard", () => ({
  MoleculeCard: ({ candidate }: { candidate: Candidate }) => (
    <div data-testid="molcard">{candidate.smiles}</div>
  ),
}));
vi.mock("../components/MoleculeEditorModal", () => ({ MoleculeEditorModal: () => null }));
vi.mock("./SaveToLibraryModal", () => ({ SaveToLibraryModal: () => null }));

function cand(mod: string, passed = true): Candidate {
  return {
    smiles: `${mod}-smiles`,
    inchikey: mod,
    modification: mod,
    properties: {},
    passed_filters: passed,
    score: 1,
  };
}

/** Render, start a run, and hand back the stream handlers the screen registered. */
function startRun(): DesignStreamHandlers {
  let handlers: DesignStreamHandlers = {};
  streamDesign.mockImplementation((_goal: string, _seed: string, h: DesignStreamHandlers) => {
    handlers = h;
    return () => {};
  });
  render(<DesignScreen />);
  fireEvent.click(screen.getByRole("button", { name: /run design/i }));
  expect(streamDesign).toHaveBeenCalledTimes(1);
  return handlers;
}

describe("DesignScreen streaming state", () => {
  it("appends candidates as they stream and re-orders on the final ranking", () => {
    const h = startRun();

    act(() => h.onPlan?.("CCO", { max_analogs: 5, constraints: {}, rationale: "r" }));
    act(() => {
      h.onCandidate?.(cand("A"));
      h.onCandidate?.(cand("B", false));
    });

    let cards = screen.getAllByTestId("molcard");
    expect(cards.map((c) => c.textContent)).toEqual(["A-smiles", "B-smiles"]);
    expect(screen.getByText("2 generated · 1 passed")).toBeInTheDocument();

    // server's authoritative ranking puts B before A
    act(() => h.onRanked?.(["B", "A"]));
    cards = screen.getAllByTestId("molcard");
    expect(cards.map((c) => c.textContent)).toEqual(["B-smiles", "A-smiles"]);
  });

  it("surfaces the run's export links and explanation on completion", () => {
    const h = startRun();

    act(() =>
      h.onComplete?.({
        run_id: "run-1",
        goal: "g",
        parent_smiles: "CCO",
        plan: { max_analogs: 1, constraints: {}, rationale: "r" },
        candidates: [cand("A")],
        trace: [],
        explanation: "why these analogs",
        models_used: {},
      }),
    );

    expect(screen.getByText("why these analogs")).toBeInTheDocument();
    expect(screen.getByText(/notebook/)).toBeInTheDocument();
    expect(screen.getByText(/report/)).toBeInTheDocument();
  });
});
