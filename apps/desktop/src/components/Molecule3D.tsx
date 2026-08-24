import { useEffect, useRef, useState } from "react";
import { api, ApiError } from "../lib/api";
import {
  elementColorscheme,
  loadMol3D,
  viewerBackground,
  type Mol3DViewer,
} from "../lib/mol3d";
import { useTheme } from "../hooks/useTheme";

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
  // The WebGL canvas cannot inherit a CSS background, so the viewer has to be
  // re-driven when the theme changes rather than left to repaint itself.
  const theme = useTheme();

  useEffect(() => {
    let cancelled = false;
    let viewer: Mol3DViewer | null = null;
    setLoading(true);
    setError(null);

    Promise.all([api.conformer(smiles), loadMol3D()])
      .then(([conf, $3Dmol]) => {
        if (cancelled || !hostRef.current) return;
        const background = viewerBackground();
        viewer = $3Dmol.createViewer(hostRef.current, { backgroundColor: background });
        viewer.setBackgroundColor(background, 1);
        viewer.addModel(conf.molblock, "mol");
        viewer.setStyle(
          {},
          {
            // CPK, stated rather than left to 3Dmol's implicit default, so the
            // 2D and 3D views of one molecule cannot drift apart.
            stick: { radius: 0.13, colorscheme: elementColorscheme() },
            sphere: { scale: 0.24, colorscheme: elementColorscheme() },
          },
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
  }, [smiles, theme]);

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
