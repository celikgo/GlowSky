import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import type { ToolRunResult } from "../lib/api";
import { SarScreen } from "./SarScreen";

const { runTool } = vi.hoisted(() => ({ runTool: vi.fn() }));

vi.mock("../lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../lib/api")>();
  return { ...actual, api: { ...actual.api, runTool } };
});

const prov = {} as ToolRunResult["provenance"];

function mockTools() {
  runTool.mockImplementation((name: string): Promise<ToolRunResult> => {
    if (name === "sar_transforms") {
      return Promise.resolve({
        output: {
          property: "logp",
          n_molecules: 5,
          n_transforms: 2,
          transforms: [
            { transformation: "[*:1][H]>>[*:1]F", n: 3, mean_delta: 0.14, median_delta: 0.14, min_delta: 0, max_delta: 0.3 },
            { transformation: "[*:1][H]>>[*:1]C", n: 2, mean_delta: -0.5, median_delta: -0.5, min_delta: -0.6, max_delta: -0.4 },
          ],
        },
        provenance: prov,
      });
    }
    if (name === "matched_pairs") {
      return Promise.resolve({
        output: {
          property: "logp",
          n_molecules: 5,
          n_pairs: 1,
          pairs: [
            { a: "c1ccccc1C(=O)O", b: "Fc1ccccc1C(=O)O", transformation: "[*:1][H]>>[*:1]F", context: "ctx", value_a: 1, value_b: 1.14, delta: 0.14 },
          ],
        },
        provenance: prov,
      });
    }
    return Promise.reject(new Error(`unexpected tool ${name}`));
  });
}

describe("SarScreen", () => {
  it("mines both tools and renders the transforms and matched-pairs tables", async () => {
    mockTools();

    render(<SarScreen />);
    fireEvent.click(screen.getByRole("button", { name: /mine sar/i }));

    // transforms table populated (ranked transform rows)
    expect(await screen.findByText("[*:1][H]>>[*:1]C")).toBeInTheDocument();

    // both tools called with the chosen property
    expect(runTool).toHaveBeenCalledWith("sar_transforms", expect.objectContaining({ property: "logp", min_count: 1 }));
    expect(runTool).toHaveBeenCalledWith("matched_pairs", expect.objectContaining({ property: "logp" }));

    // two datatables: transforms + pairs
    expect(document.querySelectorAll("table.datatable")).toHaveLength(2);

    // signed formatting + colour classing
    expect(screen.getAllByText("-0.50").length).toBeGreaterThan(0);
    expect(screen.getAllByText("+0.14").length).toBeGreaterThan(0);
  });

  it("refuses a set with fewer than two molecules", () => {
    render(<SarScreen />);
    fireEvent.change(screen.getByRole("textbox"), { target: { value: "CCO" } });
    fireEvent.click(screen.getByRole("button", { name: /mine sar/i }));

    expect(screen.getByText(/at least two molecules/)).toBeInTheDocument();
    expect(runTool).not.toHaveBeenCalled();
  });
});
