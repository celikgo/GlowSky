/**
 * Modal wrapper around the Ketcher 2D editor. Lets a chemist **draw** a structure instead
 * of pasting SMILES, then hands the canonical SMILES back to the caller via `onUse`.
 *
 * Ketcher is `React.lazy`-loaded (see `KetcherEditor`), so opening this modal is the only
 * thing that pulls the heavy editor + WASM into the page.
 */
import { Suspense, lazy, useRef, useState } from "react";
import type { Ketcher } from "ketcher-core";

const KetcherEditor = lazy(() => import("./KetcherEditor"));

export function MoleculeEditorModal({
  open,
  initialSmiles,
  title = "Draw molecule",
  onClose,
  onUse,
}: {
  open: boolean;
  initialSmiles?: string;
  title?: string;
  onClose: () => void;
  onUse: (smiles: string) => void;
}) {
  const ketcherRef = useRef<Ketcher | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (!open) return null;

  async function useStructure() {
    const ketcher = ketcherRef.current;
    if (!ketcher) return;
    setBusy(true);
    setError(null);
    try {
      const smiles = (await ketcher.getSmiles()).trim();
      if (!smiles) {
        setError("The canvas is empty — draw a structure first.");
        return;
      }
      onUse(smiles);
    } catch {
      setError("Could not read the structure. Try cleaning it up (the eraser/layout tools).");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="editor-overlay" onClick={onClose}>
      <div className="editor-modal" onClick={(e) => e.stopPropagation()}>
        <div className="editor-modal__head">
          <span className="editor-modal__title">{title}</span>
          <button className="editor-modal__close" onClick={onClose} aria-label="Close editor">
            ✕
          </button>
        </div>
        <div className="editor-modal__canvas">
          <Suspense
            fallback={
              <div className="placeholder">
                <span className="spinner" /> Loading editor…
              </div>
            }
          >
            <KetcherEditor
              initialSmiles={initialSmiles}
              onReady={(k) => {
                ketcherRef.current = k;
              }}
            />
          </Suspense>
        </div>
        <div className="editor-modal__actions">
          {error ? <span className="editor-modal__error">{error}</span> : null}
          <span className="library__spacer" />
          <button className="btn btn--ghost" onClick={onClose}>
            Cancel
          </button>
          <button className="btn" onClick={useStructure} disabled={busy}>
            {busy ? <span className="spinner" /> : null}
            Use structure
          </button>
        </div>
      </div>
    </div>
  );
}
