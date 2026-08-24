import { CPK_3D, VIEWER_CANVAS, hexToInt } from "../theme/cpk";
import { readToken } from "../theme/theme";

/**
 * Lazy, shared loader for 3Dmol.js. The library is ~600 KB, so it's dynamically
 * imported (and cached here) on first use — only paid once a molecule is viewed in 3D.
 */
export interface Mol3DModel {
  // opaque GLModel handle used as a selection target
  _id?: number;
}

export interface Mol3DViewer {
  addModel: (data: string, format: string) => Mol3DModel;
  setStyle: (sel: object, style: object) => void;
  addSurface: (type: unknown, style: object, atomsel?: object) => void;
  setBackgroundColor: (color: number, alpha: number) => void;
  zoomTo: (sel?: object) => void;
  render: () => void;
  resize: () => void;
  clear: () => void;
}

export interface Mol3D {
  createViewer: (el: HTMLElement, config?: object) => Mol3DViewer;
  SurfaceType: { VDW: unknown; SAS: unknown; MS: unknown };
}

/**
 * An explicit 3Dmol colorscheme built from CPK_3D.
 *
 * 3Dmol's implicit default is already the Jmol table, but stating it here means
 * the element colours the 3D views use are declared in this repository rather
 * than left inside a vendored bundle — which is how the 2D and 3D depictions
 * of the same molecule came to disagree in the first place. `carbon` overrides
 * the skeleton without touching any heteroatom; a docked ligand uses it to
 * separate itself from the receptor, which is a figure convention, not an
 * element colour. See src/theme/cpk.ts.
 */
export function elementColorscheme(carbon?: string): { prop: string; map: Record<string, string> } {
  return { prop: "elem", map: carbon ? { ...CPK_3D, C: carbon } : { ...CPK_3D } };
}

let pending: Promise<Mol3D> | null = null;

export function loadMol3D(): Promise<Mol3D> {
  if (!pending) {
    pending = import("3dmol/build/3Dmol.es6.js").then((m) => m as unknown as Mol3D);
  }
  return pending;
}

/**
 * The viewport's clear colour, as the packed int 3Dmol wants.
 *
 * Read from --viewer-canvas rather than pinned, but note that token is
 * identical in all three themes on purpose: 3D molecular graphics use the Jmol
 * element colours, several of which (hydrogen at 1.00:1, sulfur at 1.07:1)
 * simply vanish on a light ground. Element colour is chemical identity and is
 * not re-tinted to suit the chrome, so the ground is what stays put instead.
 * `apps/desktop/src/theme/cpk.ts` carries the measurements.
 */
export function viewerBackground(): number {
  return hexToInt(readToken("--viewer-canvas") || VIEWER_CANVAS);
}
