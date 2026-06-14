# Glowsky Desktop

The Glowsky desktop app — a **Tauri 2 + React + Vite + TypeScript** shell for the
AI-native small-molecule design workspace. The UI talks to the Glowsky FastAPI backend
over HTTP; the chemistry/agent compute lives there, not in the client.

Themed in the **Twitter "Dim"** palette (the blue-tinted dark theme). All colors come
from a single tokens file — `src/theme/tokens.css` — so the whole app re-skins from one
place.

## Prerequisites

- Node ≥ 18 + **pnpm**
- Rust (stable) + the Tauri 2 system deps for your OS — see
  https://v2.tauri.app/start/prerequisites/
- The Glowsky backend running at `http://localhost:8000` (`make run` in the repo root)

## Develop

```bash
pnpm install
pnpm dev          # web UI only, in the browser at http://localhost:1420
pnpm desktop      # the full desktop app (Tauri window) — runs `pnpm dev` for you
```

Point the UI at a non-default backend with `VITE_API_BASE`:

```bash
VITE_API_BASE=http://127.0.0.1:9000 pnpm dev
```

## Build

```bash
pnpm build           # type-check + bundle the web assets to dist/
pnpm desktop:build   # produce a native installer (.dmg/.app, .msi, .deb/.AppImage)
```

## Layout

```
src/
  theme/        tokens.css (the Twitter Dim palette) + global.css primitives
  lib/api.ts    typed FastAPI client (health, design, profile, run export)
  lib/rdkit.ts  lazy single-flight loader for the RDKit-JS WASM module
  hooks/useRDKit.ts   React hook exposing the RDKit module when ready
  components/    Sidebar, TopBar (health pill), MoleculeStructure (RDKit 2D SVG)
  screens/       DesignScreen (the agentic design loop), MoleculeCard, Placeholder
src-tauri/      the Rust shell (window config, icons, capabilities)
```

## What works now

The **Design** screen drives the backend's agentic design loop end-to-end: enter a
natural-language goal + a seed SMILES, run it, and see the plan, candidate molecules
with **2D structure depictions** (rendered client-side by RDKit-JS), property chips,
pass/fail, the agent's explanation, and the execution trace — plus one-click
notebook/report export of the run. Library / Tools / Settings are placeholders whose
backend seams already exist.

### 2D structure rendering (RDKit-JS, offline)

Structures are drawn in-browser by the **RDKit WebAssembly** build (`@rdkit/rdkit`) —
no server round-trip, no CDN. `scripts/copy-rdkit.mjs` stages the loader + `.wasm`
(~6.9 MB) into `public/` on install / before dev / before build; the module loads lazily
and instantiates once (`src/lib/rdkit.ts`), so the app bundle stays ~150 KB. Each
`MoleculeStructure` validates the SMILES and frees the WASM-side molecule after drawing.

## Troubleshooting

- **`brotli` fails to compile (`alloc-no-stdlib` trait mismatch).** A transitive of
  Tauri; `alloc-no-stdlib` is pinned to 2.x in the committed `Cargo.lock`. If you run
  `cargo update` and hit this again, re-pin with
  `cargo update -p alloc-no-stdlib --precise 2.0.4`.
- **pnpm blocks esbuild's install script.** `.npmrc` sets `verify-deps-before-run=false`
  and `package.json` allowlists esbuild via `pnpm.onlyBuiltDependencies`.

## Regenerating icons

Icons were generated from `src-tauri/source-icon.png` with `cargo tauri icon`. Replace
that source and re-run it to rebrand.
