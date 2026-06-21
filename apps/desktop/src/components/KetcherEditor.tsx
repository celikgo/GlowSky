/**
 * The Ketcher 2D structure editor, isolated behind a default export so it can be
 * `React.lazy`-loaded — Ketcher + its Indigo WASM engine are heavy, and a chemist only
 * pays that cost when they actually open the editor (the rest of the app stays light).
 *
 * Standalone mode: the `StandaloneStructServiceProvider` runs Indigo entirely in a Web
 * Worker (loaded via Vite's native `new Worker(new URL(...))`), so the editor draws,
 * cleans, and emits SMILES with **no backend and no network** — same offline-first
 * stance as the RDKit-JS depiction layer. Node-global shims live in `vite.config.ts`.
 */
import "ketcher-react/dist/index.css";
import { Editor } from "ketcher-react";
import { StandaloneStructServiceProvider } from "ketcher-standalone";
import type { Ketcher } from "ketcher-core";

// One provider for the app — constructing it spins up the Indigo worker, so we keep it
// module-level rather than per-mount.
const structServiceProvider = new StandaloneStructServiceProvider();

export default function KetcherEditor({
  initialSmiles,
  onReady,
}: {
  initialSmiles?: string;
  onReady: (ketcher: Ketcher) => void;
}) {
  return (
    <Editor
      staticResourcesUrl=""
      structServiceProvider={structServiceProvider}
      errorHandler={(message) => console.error("[ketcher]", message)}
      onInit={(ketcher: Ketcher) => {
        onReady(ketcher);
        // Pre-load the seed structure (if any) so the chemist edits from where they are,
        // not a blank canvas. A bad/empty SMILES just leaves the canvas empty — non-fatal.
        if (initialSmiles?.trim()) {
          void ketcher.setMolecule(initialSmiles.trim()).catch(() => {});
        }
      }}
    />
  );
}
