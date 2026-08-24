/**
 * The rule this file exists to hold: a theme change must not move an element
 * colour.
 *
 * Before the theme system there was a single `DARK_DRAW_OPTIONS` constant in
 * which oxygen was #FF7373 and nitrogen #6BA3FF — CPK hues lightened until they
 * read well on the Dim surface. That is exactly the failure mode: colours a
 * chemist reads as identity, adjusted to suit the chrome. The test below
 * renders the same molecule under every theme and asserts the palette RDKit is
 * handed is byte-identical each time.
 */
import { describe, expect, it, vi } from "vitest";
import { render } from "@testing-library/react";
import { MoleculeStructure } from "./MoleculeStructure";
import { CPK_2D, hexToRgbFloat } from "../theme/cpk";
import { THEMES, applyTheme } from "../theme/theme";

const { getMol } = vi.hoisted(() => ({ getMol: vi.fn() }));

// The real hook loads a 6 MB WASM module; the drawing options are what matter.
vi.mock("../hooks/useRDKit", () => ({ useRDKit: () => ({ get_mol: getMol }) }));

/** Render once under `theme` and return the options object RDKit was given. */
function drawOptionsUnder(theme: (typeof THEMES)[number]): Record<string, unknown> {
  const drawn = vi.fn((_options: string) => "<svg />");
  getMol.mockReturnValue({ is_valid: () => true, get_svg_with_highlights: drawn, delete: () => {} });
  applyTheme(theme);
  render(<MoleculeStructure smiles="CC(=O)Nc1ccc(O)cc1" />);
  expect(drawn).toHaveBeenCalledTimes(1);
  return JSON.parse(drawn.mock.calls[0][0]) as Record<string, unknown>;
}

describe("element colours are chemical data, not theme", () => {
  it("hands RDKit the same atom palette in every theme", () => {
    const palettes = THEMES.map((theme) => drawOptionsUnder(theme).atomColourPalette);
    for (const palette of palettes) {
      expect(palette).toEqual(palettes[0]);
    }
  });

  it("hands RDKit the CPK palette, not a lightened one", () => {
    const palette = drawOptionsUnder("dim").atomColourPalette as Record<string, number[]>;
    // Oxygen red and nitrogen blue, the two a chemist reads first. Sulfur is
    // brown rather than the familiar yellow in this palette — see cpk.ts for
    // why that trade was taken; the test asserts the constant, not a hue.
    expect(palette["8"]).toEqual(hexToRgbFloat(CPK_2D["8"]));
    expect(palette["7"]).toEqual(hexToRgbFloat(CPK_2D["7"]));
    expect(palette["16"]).toEqual(hexToRgbFloat(CPK_2D["16"]));
    expect(Object.keys(palette).sort()).toEqual(Object.keys(CPK_2D).sort());
  });

  it("draws on the molecule ground rather than on the theme's surface", () => {
    for (const theme of THEMES) {
      expect(drawOptionsUnder(theme).backgroundColour).toEqual(drawOptionsUnder("dim").backgroundColour);
    }
  });

  it("degrades to a placeholder rather than throwing on an unparseable structure", () => {
    getMol.mockReturnValue(null);
    const { container } = render(<MoleculeStructure smiles="not-a-smiles" />);
    expect(container.querySelector(".molstruct--empty")).not.toBeNull();
  });
});
