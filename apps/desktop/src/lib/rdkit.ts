/**
 * Lazy, single-flight loader for the RDKit-JS WASM module.
 *
 * The emscripten loader (`window.initRDKitModule`) is injected once via a <script> tag
 * pointing at the assets staged under public/ (see scripts/copy-rdkit.mjs). All callers
 * share one in-flight promise, so the 6.9 MB WASM is fetched and instantiated exactly
 * once for the whole app.
 */
import type { RDKitModule } from "@rdkit/rdkit";

const RDKIT_JS = "/RDKit_minimal.js";
const RDKIT_WASM = "/RDKit_minimal.wasm";

let pending: Promise<RDKitModule> | null = null;

function injectScript(): Promise<void> {
  return new Promise((resolve, reject) => {
    // initRDKitModule only exists after the loader script runs; the package types it as
    // always-present, so probe through an optional cast.
    if ((window as { initRDKitModule?: unknown }).initRDKitModule) return resolve();
    const existing = document.querySelector<HTMLScriptElement>(`script[src="${RDKIT_JS}"]`);
    if (existing) {
      existing.addEventListener("load", () => resolve());
      existing.addEventListener("error", () => reject(new Error("failed to load RDKit-JS")));
      return;
    }
    const el = document.createElement("script");
    el.src = RDKIT_JS;
    el.async = true;
    el.onload = () => resolve();
    el.onerror = () => reject(new Error("failed to load RDKit-JS"));
    document.head.appendChild(el);
  });
}

export function loadRDKit(): Promise<RDKitModule> {
  if (pending) return pending;
  pending = injectScript()
    .then(() => window.initRDKitModule({ locateFile: () => RDKIT_WASM }))
    .catch((err) => {
      pending = null; // allow a later retry
      throw err;
    });
  return pending;
}
