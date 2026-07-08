import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import type { ToolRunResult, ToolSpec } from "../lib/api";
import { ToolsScreen } from "./ToolsScreen";

const { listTools, runTool } = vi.hoisted(() => ({ listTools: vi.fn(), runTool: vi.fn() }));

vi.mock("../lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../lib/api")>();
  return { ...actual, api: { ...actual.api, listTools, runTool } };
});

// The registry playground draws structures from results; short-circuit the RDKit WASM hook.
vi.mock("../hooks/useRDKit", () => ({ useRDKit: () => null }));

function tool(name: string, category: string): ToolSpec {
  return {
    name,
    version: "1",
    category,
    description: `desc for ${name}`,
    parameters: { type: "object", properties: { canonical_smiles: { type: "string" } }, required: ["canonical_smiles"] },
    compute_class: "cpu_light",
    latency_class: "short",
    emits_structures: false,
  };
}

const PROV = {
  tool: "retrosynthesize",
  version: "1",
  compute_class: "cpu_light",
  determinism: "deterministic",
  env_digest: "e",
  input_hash: "h",
  cache_hit: false,
  duration_ms: 12,
  seed: null,
  error: null,
};

describe("ToolsScreen", () => {
  it("renders the registry grouped by category and auto-selects the first tool", async () => {
    listTools.mockResolvedValue([tool("retrosynthesize", "cheminformatics"), tool("mpo_score", "property")]);

    render(<ToolsScreen />);

    // first tool auto-selected → its parameter form (heading) is shown once loaded
    expect(await screen.findByRole("heading", { name: "retrosynthesize" })).toBeInTheDocument();
    // both tools listed, under their category headers. "cheminformatics" appears twice — as the
    // group header and as the auto-selected tool's category chip — so assert presence, not uniqueness.
    expect(screen.getByText("mpo_score")).toBeInTheDocument();
    expect(screen.getAllByText("cheminformatics").length).toBeGreaterThan(0);
    expect(screen.getByText("property")).toBeInTheDocument();
    expect(screen.getByText(/canonical_smiles/)).toBeInTheDocument();
  });

  it("invokes runTool with the prefilled args and renders the provenance + output", async () => {
    listTools.mockResolvedValue([tool("retrosynthesize", "cheminformatics")]);
    const result: ToolRunResult = { output: { target: "CCO", n_disconnections: 0 }, provenance: PROV };
    runTool.mockResolvedValue(result);

    render(<ToolsScreen />);
    await screen.findByRole("heading", { name: "retrosynthesize" });

    fireEvent.click(screen.getByRole("button", { name: /run tool/i }));

    expect(await screen.findByText("Result")).toBeInTheDocument();
    expect(runTool).toHaveBeenCalledTimes(1);
    const [name, args] = runTool.mock.calls[0] as [string, Record<string, unknown>];
    expect(name).toBe("retrosynthesize");
    expect(args.canonical_smiles).toBeTruthy();
    // provenance chip from the run
    expect(screen.getByText("12 ms")).toBeInTheDocument();
    expect(screen.getByText("computed")).toBeInTheDocument();
  });
});
