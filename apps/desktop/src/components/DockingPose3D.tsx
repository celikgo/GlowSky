import { useEffect, useRef, useState } from "react";
import {
  elementColorscheme,
  loadMol3D,
  viewerBackground,
  type Mol3DViewer,
} from "../lib/mol3d";
import { useTheme } from "../hooks/useTheme";
import { LIGAND_CARBON } from "../theme/cpk";
import { readToken } from "../theme/theme";

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
  // See Molecule3D: a WebGL canvas has to be told about a theme change.
  const theme = useTheme();

  useEffect(() => {
    let cancelled = false;
    let viewer: Mol3DViewer | null = null;
    setLoading(true);
    setError(null);

    loadMol3D()
      .then(($3Dmol) => {
        if (cancelled || !hostRef.current) return;
        const background = viewerBackground();
        viewer = $3Dmol.createViewer(hostRef.current, { backgroundColor: background });
        viewer.setBackgroundColor(background, 1);

        // Receptor: a spectrum cartoon plus a faint translucent pocket surface.
        const receptor = viewer.addModel(receptorPdb, "pdb");
        viewer.setStyle({ model: receptor }, { cartoon: { color: "spectrum", opacity: 0.9 } });
        viewer.addSurface(
          $3Dmol.SurfaceType.VDW,
          // A pocket surface is geometry, not an element, so it is a token.
          { opacity: 0.55, color: readToken("--viewer-surface") },
          { model: receptor },
        );

        // Ligand pose: ball-and-stick, the focus of the view. Cyan carbon is
        // the standard way a docking figure separates ligand from receptor —
        // carbon is the one element whose colour carries "which molecule is
        // this" rather than "which element is this". Every heteroatom keeps
        // its CPK colour; see src/theme/cpk.ts.
        const lig = viewer.addModel(ligand, ligandFormat);
        const ligandStyle = { colorscheme: elementColorscheme(LIGAND_CARBON) };
        viewer.setStyle(
          { model: lig },
          { stick: { radius: 0.16, ...ligandStyle }, sphere: { scale: 0.26, ...ligandStyle } },
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
  }, [receptorPdb, ligand, ligandFormat, theme]);

  return (
    <div className="pose3d" style={{ height }}>
      <div ref={hostRef} className="pose3d__canvas" style={{ height }} />
      {loading ? <div className="pose3d__overlay">rendering pose…</div> : null}
      {error ? <div className="pose3d__overlay pose3d__overlay--error">{error}</div> : null}
    </div>
  );
}
