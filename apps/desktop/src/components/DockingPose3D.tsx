import { useEffect, useRef, useState } from "react";
import { loadMol3D, SURFACE, type Mol3DViewer } from "../lib/mol3d";

/**
 * Receptor + ligand-pose overlay. Renders the receptor as a cartoon and the docked
 * ligand as a ball-and-stick model in 3Dmol.js, focused on the binding pocket. The
 * ligand may be a PDB block (the 1HSG sample) or a Vina pose .pdbqt — 3Dmol parses both.
 */
export function DockingPose3D({
  receptorPdb,
  ligand,
  ligandFormat = "pdb",
  height = 460,
}: {
  receptorPdb: string;
  ligand: string;
  ligandFormat?: "pdb" | "pdbqt";
  height?: number;
}) {
  const hostRef = useRef<HTMLDivElement>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    let viewer: Mol3DViewer | null = null;
    setLoading(true);
    setError(null);

    loadMol3D()
      .then(($3Dmol) => {
        if (cancelled || !hostRef.current) return;
        viewer = $3Dmol.createViewer(hostRef.current, { backgroundColor: SURFACE });
        viewer.setBackgroundColor(SURFACE, 1);

        // Receptor: a spectrum cartoon plus a faint translucent pocket surface.
        const receptor = viewer.addModel(receptorPdb, "pdb");
        viewer.setStyle({ model: receptor }, { cartoon: { color: "spectrum", opacity: 0.9 } });
        viewer.addSurface(
          $3Dmol.SurfaceType.VDW,
          { opacity: 0.55, color: "#8b98a5" },
          { model: receptor },
        );

        // Ligand pose: ball-and-stick, the focus of the view.
        const lig = viewer.addModel(ligand, ligandFormat);
        viewer.setStyle(
          { model: lig },
          { stick: { radius: 0.16, colorscheme: "cyanCarbon" }, sphere: { scale: 0.26 } },
        );

        viewer.zoomTo({ model: lig });
        viewer.render();
        setLoading(false);
      })
      .catch(() => {
        if (cancelled) return;
        setError("could not render the pose");
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
  }, [receptorPdb, ligand, ligandFormat]);

  return (
    <div className="pose3d" style={{ height }}>
      <div ref={hostRef} className="pose3d__canvas" style={{ height }} />
      {loading ? <div className="pose3d__overlay">rendering pose…</div> : null}
      {error ? <div className="pose3d__overlay pose3d__overlay--error">{error}</div> : null}
    </div>
  );
}
