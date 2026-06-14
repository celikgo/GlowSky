import { useEffect, useRef, useState } from "react";
import { api, ApiError } from "../lib/api";

// 3Dmol.js is ~hundreds of KB and only needed once a card is flipped to 3D, so it's
// dynamically imported (and cached by the module loader) on first mount.
type Viewer = {
  addModel: (data: string, format: string) => void;
  setStyle: (sel: object, style: object) => void;
  setBackgroundColor: (color: number, alpha: number) => void;
  zoomTo: () => void;
  render: () => void;
  resize: () => void;
  clear: () => void;
};
type Mol3D = { createViewer: (el: HTMLElement, config?: object) => Viewer };

let mol3dPending: Promise<Mol3D> | null = null;
function loadMol3D(): Promise<Mol3D> {
  if (!mol3dPending) {
    mol3dPending = import("3dmol/build/3Dmol.es6.js").then((m) => m as unknown as Mol3D);
  }
  return mol3dPending;
}

// The Dim elevated surface (var(--bg-elevated)) as an int, so the WebGL canvas blends
// into the card instead of sitting on a black rectangle.
const SURFACE = 0x1e2732;

/**
 * Interactive 3D structure viewer. Fetches a single MMFF-minimized conformer (MOL block
 * with 3D coords) from the backend for `smiles`, then renders it with 3Dmol.js as a
 * ball-and-stick model the user can rotate/zoom. Embedding failures degrade to a message
 * rather than throwing.
 */
export function Molecule3D({
  smiles,
  width = 280,
  height = 170,
}: {
  smiles: string;
  width?: number;
  height?: number;
}) {
  const hostRef = useRef<HTMLDivElement>(null);
  const [error, setError] = useState<string | null>(null);
  const [energy, setEnergy] = useState<number | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    let viewer: Viewer | null = null;
    setLoading(true);
    setError(null);

    Promise.all([api.conformer(smiles), loadMol3D()])
      .then(([conf, $3Dmol]) => {
        if (cancelled || !hostRef.current) return;
        viewer = $3Dmol.createViewer(hostRef.current, { backgroundColor: SURFACE });
        viewer.setBackgroundColor(SURFACE, 1);
        viewer.addModel(conf.molblock, "mol");
        viewer.setStyle(
          {},
          { stick: { radius: 0.13 }, sphere: { scale: 0.24 } },
        );
        viewer.zoomTo();
        viewer.render();
        setEnergy(conf.energy_kcal_mol);
        setLoading(false);
      })
      .catch((err) => {
        if (cancelled) return;
        const msg = err instanceof ApiError ? err.message : "could not embed 3D structure";
        setError(msg);
        setLoading(false);
      });

    return () => {
      cancelled = true;
      try {
        viewer?.clear();
      } catch {
        /* viewer teardown is best-effort */
      }
    };
  }, [smiles]);

  return (
    <div className="mol3d" style={{ height }}>
      <div ref={hostRef} className="mol3d__canvas" style={{ width, height }} />
      {loading ? <div className="mol3d__overlay">embedding…</div> : null}
      {error ? <div className="mol3d__overlay mol3d__overlay--error">{error}</div> : null}
      {!loading && !error && energy !== null ? (
        <span className="mol3d__energy mono">{energy.toFixed(1)} kcal/mol</span>
      ) : null}
    </div>
  );
}
