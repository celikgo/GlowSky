import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import type { ToolRunResult } from "../lib/api";
import { RetroScreen } from "./RetroScreen";

const { runTool } = vi.hoisted(() => ({ runTool: vi.fn() }));

vi.mock("../lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../lib/api")>();
  return { ...actual, api: { ...actual.api, runTool } };
});

// Stand in for the RDKit depiction so the route tree renders without the WASM module.
vi.mock("../components/MoleculeStructure", () => ({
  MoleculeStructure: ({ smiles }: { smiles: string }) => <div data-testid="mol">{smiles}</div>,
}));

describe("RetroScreen", () => {
  it("calls the retrosynthesize tool and renders each disconnection as a route", async () => {
    const result: ToolRunResult = {
      output: {
        target: "CC(=O)Nc1ccc(O)cc1",
        n_disconnections: 1,
        disconnections: [
          {
            reaction: "amide coupling",
            precursors: ["CC(=O)O", "Nc1ccc(O)cc1"],
            all_building_blocks: true,
          },
        ],
      },
      provenance: {} as ToolRunResult["provenance"],
    };
    runTool.mockResolvedValue(result);

    render(<RetroScreen />);
    fireEvent.click(screen.getByRole("button", { name: /disconnect/i }));

    expect(await screen.findByText("amide coupling")).toBeInTheDocument();
    expect(screen.getByText("building blocks")).toBeInTheDocument();

    const [name, args] = runTool.mock.calls[0] as [string, Record<string, unknown>];
    expect(name).toBe("retrosynthesize");
    expect(args.canonical_smiles).toBe("CC(=O)Nc1ccc(O)cc1");
    expect(args.max_routes).toBe(10);

    // one target depiction + two precursor depictions
    expect(screen.getAllByTestId("mol")).toHaveLength(3);
  });

  it("shows the honest empty state when no disconnection is found", async () => {
    runTool.mockResolvedValue({
      output: { target: "C", n_disconnections: 0, disconnections: [] },
      provenance: {} as ToolRunResult["provenance"],
    });

    render(<RetroScreen />);
    fireEvent.click(screen.getByRole("button", { name: /disconnect/i }));

    expect(await screen.findByText(/No recognised one-step disconnection/)).toBeInTheDocument();
  });
});
