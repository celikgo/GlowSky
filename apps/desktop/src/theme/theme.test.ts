/**
 * The theme contract, and the one copy of it that lives outside TypeScript.
 *
 * index.html applies the theme before React mounts, because applying it after
 * means a frame of the wrong theme on every launch. That inline script is a
 * hand-written copy of readChoice + resolveTheme, and a copy nobody checks is
 * a copy that drifts — so it is checked here.
 */
import { describe, expect, it } from "vitest";
// `?raw` rather than node:fs: vite resolves these, so the test needs no node
// typings and the paths are checked at build time instead of at runtime.
import indexHtml from "../../index.html?raw";
import {
  DEFAULT_CHOICE,
  STORAGE_KEY,
  THEMES,
  THEME_CHOICES,
  THEME_LABELS,
  applyTheme,
  readChoice,
  resolveTheme,
  storeChoice,
} from "./theme";

describe("theme selection", () => {
  it("falls back to the default when nothing is stored", () => {
    expect(readChoice()).toBe(DEFAULT_CHOICE);
  });

  it("ignores a stored value that is not a theme, rather than applying it", () => {
    localStorage.setItem(STORAGE_KEY, "midnight-purple");
    expect(readChoice()).toBe(DEFAULT_CHOICE);
  });

  it("round-trips a stored choice", () => {
    storeChoice("light");
    expect(readChoice()).toBe("light");
  });

  it("resolves 'system' to dim rather than lights-out — lights-out is chosen, never inferred", () => {
    // setup.ts's matchMedia reports `matches: false` for the light query.
    expect(resolveTheme("system")).toBe("dim");
  });

  it("puts the theme on the document element, where tokens.css selects on it", () => {
    applyTheme("lights-out");
    expect(document.documentElement.getAttribute("data-theme")).toBe("lights-out");
  });

  it("offers every theme, plus system, and labels all of them", () => {
    expect(THEME_CHOICES).toEqual(["system", ...THEMES]);
    for (const choice of THEME_CHOICES) {
      expect(THEME_LABELS[choice]).toBeTruthy();
    }
  });
});

// That tokens.css defines a block for each of THEMES is checked by
// scripts/check_design_tokens.py, which parses both files — vitest stubs CSS
// imports out entirely, so it cannot see the stylesheet to check it here.

describe("the pre-paint script in index.html has not drifted from this module", () => {
  it("reads the same storage key", () => {
    expect(indexHtml).toContain(`localStorage.getItem("${STORAGE_KEY}")`);
  });

  it("accepts exactly the choices this module accepts", () => {
    const listed = indexHtml.match(/var CHOICES = \[([^\]]*)\]/);
    expect(listed).not.toBeNull();
    const parsed = JSON.parse(`[${listed![1]}]`) as string[];
    expect(parsed).toEqual([...THEME_CHOICES]);
  });

  it("applies the same default", () => {
    expect(indexHtml).toContain(`var choice = "${DEFAULT_CHOICE}"`);
    expect(indexHtml).toContain(`<html lang="en" data-theme="${DEFAULT_CHOICE}">`);
  });

  it("maps 'system' the same way — light preference to light, everything else to dim", () => {
    expect(indexHtml).toContain('"(prefers-color-scheme: light)"');
    expect(indexHtml).toContain('? "light"\n              : "dim"');
  });

  it("sets the attribute this module sets", () => {
    expect(indexHtml).toContain('document.documentElement.setAttribute("data-theme", choice)');
  });
});
