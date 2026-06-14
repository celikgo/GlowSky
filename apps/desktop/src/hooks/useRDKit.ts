import { useEffect, useState } from "react";
import type { RDKitModule } from "@rdkit/rdkit";
import { loadRDKit } from "../lib/rdkit";

// Process-wide cache so the module instantiates once and re-renders are cheap.
let cached: RDKitModule | null = null;

/** Returns the RDKit module once the WASM is ready, or null while it loads. */
export function useRDKit(): RDKitModule | null {
  const [rdkit, setRdkit] = useState<RDKitModule | null>(cached);

  useEffect(() => {
    if (cached) return;
    let live = true;
    loadRDKit()
      .then((m) => {
        cached = m;
        if (live) setRdkit(m);
      })
      .catch((err) => console.error("RDKit failed to load:", err));
    return () => {
      live = false;
    };
  }, []);

  return rdkit;
}
