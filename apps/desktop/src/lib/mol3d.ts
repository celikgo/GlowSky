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

let pending: Promise<Mol3D> | null = null;

export function loadMol3D(): Promise<Mol3D> {
  if (!pending) {
    pending = import("3dmol/build/3Dmol.es6.js").then((m) => m as unknown as Mol3D);
  }
  return pending;
}

// The Dim elevated surface (var(--bg-elevated)) as an int, so the WebGL canvas blends
// into the surrounding card/panel instead of a black rectangle.
export const SURFACE = 0x1e2732;
