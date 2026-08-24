import { useSyncExternalStore } from "react";
import {
  applyTheme,
  readChoice,
  resolveTheme,
  storeChoice,
  type Theme,
  type ThemeChoice,
} from "../theme/theme";

/**
 * The live theme, as a store rather than a context.
 *
 * A context would need a provider wrapped around the app, and the two things
 * that most need to hear about a theme change — the RDKit depiction and the
 * 3Dmol viewer — are deep in the tree and re-render on their own schedule.
 * A module-level store with useSyncExternalStore reaches them without
 * threading a provider through, and it is also what lets a "system" choice
 * follow the OS while the app is running.
 */

const listeners = new Set<() => void>();
let choice: ThemeChoice = readChoice();
let theme: Theme = resolveTheme(choice);

function emit(): void {
  applyTheme(theme);
  for (const listener of listeners) listener();
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  // Only worth watching while something is subscribed, and only meaningful
  // for the "system" choice — but the query is cheap and unsubscribing on
  // every choice change would be more code than it saves.
  const media =
    typeof window !== "undefined" && typeof window.matchMedia === "function"
      ? window.matchMedia("(prefers-color-scheme: light)")
      : null;
  const onSystemChange = () => {
    if (choice !== "system") return;
    theme = resolveTheme(choice);
    emit();
  };
  media?.addEventListener("change", onSystemChange);
  return () => {
    listeners.delete(listener);
    media?.removeEventListener("change", onSystemChange);
  };
}

export function setThemeChoice(next: ThemeChoice): void {
  choice = next;
  theme = resolveTheme(next);
  storeChoice(next);
  emit();
}

/** The resolved theme name. Components re-render when it changes. */
export function useTheme(): Theme {
  return useSyncExternalStore(
    subscribe,
    () => theme,
    () => theme,
  );
}

/** What the user actually picked, which may be "system". */
export function useThemeChoice(): ThemeChoice {
  return useSyncExternalStore(
    subscribe,
    () => choice,
    () => choice,
  );
}

/** Apply the stored choice at startup, after index.html's pre-paint guess. */
export function initTheme(): void {
  choice = readChoice();
  theme = resolveTheme(choice);
  applyTheme(theme);
}
