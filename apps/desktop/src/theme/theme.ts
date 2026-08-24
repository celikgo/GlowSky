/**
 * Theme selection: which `data-theme` block in tokens.css is live.
 *
 * Deliberately framework-free. The same three facts — the storage key, the
 * theme names, and how "system" resolves — are needed by the inline script in
 * index.html that runs BEFORE React mounts, and a theme applied after first
 * paint is a white flash on a dark app (or worse, the reverse). index.html
 * carries a hand-inlined copy of the resolve step for that reason; the copy is
 * ten lines long and `apps/desktop/src/theme/theme.test.ts` asserts it agrees
 * with this file, so it cannot drift.
 */

/** The themes defined in tokens.css, in the order the Settings screen lists them. */
export const THEMES = ["dim", "light", "lights-out"] as const;
export type Theme = (typeof THEMES)[number];

/** What the user picked. "system" follows the OS's light/dark preference. */
export type ThemeChoice = Theme | "system";
export const THEME_CHOICES = ["system", ...THEMES] as const;

export const DEFAULT_CHOICE: ThemeChoice = "dim";
export const STORAGE_KEY = "glowsky.theme";

/** Human labels for the switcher. */
export const THEME_LABELS: Record<ThemeChoice, string> = {
  system: "Match system",
  dim: "Dim",
  light: "Light",
  "lights-out": "Lights out",
};

function isChoice(value: string | null): value is ThemeChoice {
  return value !== null && (THEME_CHOICES as readonly string[]).includes(value);
}

/** The stored choice, or the default. Never throws: a Tauri webview with
 *  storage disabled must still render, and it renders in the default theme. */
export function readChoice(): ThemeChoice {
  try {
    const stored = localStorage.getItem(STORAGE_KEY);
    return isChoice(stored) ? stored : DEFAULT_CHOICE;
  } catch {
    // Storage can be unavailable (private mode, a locked-down webview). The
    // theme is a preference, not state the app needs, so this is not an error.
    return DEFAULT_CHOICE;
  }
}

export function storeChoice(choice: ThemeChoice): void {
  try {
    localStorage.setItem(STORAGE_KEY, choice);
  } catch {
    // See readChoice: losing the preference is survivable, crashing is not.
  }
}

/** "system" means the OS's dark preference maps to dim, not to lights-out —
 *  lights-out is an OLED choice a user makes deliberately, never one inferred. */
export function systemTheme(): Theme {
  if (typeof window === "undefined" || typeof window.matchMedia !== "function") {
    return "dim";
  }
  return window.matchMedia("(prefers-color-scheme: light)").matches ? "light" : "dim";
}

export function resolveTheme(choice: ThemeChoice): Theme {
  return choice === "system" ? systemTheme() : choice;
}

export function applyTheme(theme: Theme): void {
  document.documentElement.setAttribute("data-theme", theme);
}

/**
 * The computed value of a design token, for the two viewers that paint onto a
 * canvas CSS cannot reach (RDKit's SVG generator and 3Dmol's WebGL context).
 * Returns "" when the stylesheet has not been applied — under vitest, where
 * CSS is not processed, callers fall back to the ground declared in cpk.ts.
 */
export function readToken(name: string): string {
  if (typeof window === "undefined") return "";
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
}
