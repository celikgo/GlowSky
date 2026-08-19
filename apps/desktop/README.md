# Glowsky Desktop

The Glowsky desktop app — a **Tauri 2 + React 18 + Vite + TypeScript** shell for the
AI-native small-molecule design workspace. The UI talks to the Glowsky FastAPI backend
over HTTP, with the agentic design and Composer chat loops streaming milestone events
over WebSockets (`WS /agent/design/stream`, `WS /agent/chat/stream` — the JWT rides the
init frame, since a WebSocket can't send an `Authorization` header); the chemistry/agent
compute lives there, not in the client.

Themed in the **Twitter "Dim"** palette (the blue-tinted dark theme). All colors come
from a single tokens file — `src/theme/tokens.css` — so the whole app re-skins from one
place.

## Prerequisites

- Node ≥ 18 + **pnpm**
- Rust (stable) + the Tauri 2 system deps for your OS — see
  https://v2.tauri.app/start/prerequisites/
- The Glowsky backend running at `http://localhost:8000` (`make run` in the repo root)
- A **nakitte-carbon-auth** account, with the backend pointed at your identity service
  (`GLOWSKY_NAKITTE_AUTH_URL` / `GLOWSKY_NAKITTE_JWKS_URL`, both defaulting to a service
  on `http://localhost:8081`). A platform JWT is the backend's only credential — there is
  no auth bypass in any environment.

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

### Sign in

The app has no login gate — it opens on the Composer regardless of auth state, the health
pill still goes green ("Backend online · 22 tools") because `GET /health` is
unauthenticated, and the Tools screen can list the registry because `GET /tools` is too.
Everything that touches your data is not: projects, libraries, runs, `POST /tools/{name}`
and the `/agent/*` endpoints all 401 without a token, and the agent WebSockets accept the
socket only to relay an `error` frame (`missing token`) and close. (The only other open
routes are the login proxy — `POST /auth/login`, `POST /auth/refresh`,
`GET /auth/tenants`, `POST /auth/select-tenant` — plus `POST /molecules/diff` and
`GET /settings/providers`.)

So go to **Settings → Platform access** first and sign in with your carbon-auth email +
password (proxied through the backend; your password is never stored). If your account
belongs to two or more tenants you'll then pick a workspace. Alternatively, expand
"Paste a token directly" and paste a bearer JWT. Access and refresh tokens are kept in
`localStorage` (`glowsky_token` / `glowsky_refresh_token`) and the session refreshes
silently; `VITE_AUTH_TOKEN` is a Vite-time fallback for local hacking. Until you sign in,
anything you load or run fails — surfaced only as per-screen text such as "Sign in (paste
a token in Settings) to load the assessment."

## Build

```bash
pnpm build           # type-check + bundle the web assets to dist/
pnpm desktop:build   # produce a native installer (.dmg/.app, .msi, .deb/.AppImage)
```

## Test

```bash
pnpm test        # vitest run — 13 tests across 5 files
pnpm test:watch  # watch mode
pnpm typecheck   # tsc --noEmit (also run by `pnpm build`)
```

Tests use a standalone `vitest.config.ts` (jsdom, globals, `clearMocks`) kept apart from
`vite.config.ts` so the Ketcher CJS pre-bundling (`optimizeDeps.include`) and the
node-global polyfills the app build needs don't run under the tests. `src/test/setup.ts`
loads the jest-dom matchers and swaps in an in-memory `Storage` shim, because jsdom in
this env exposes `localStorage` as a bare object.

Coverage today is `src/lib/api.ts` (tool invocation, optional seed, `ApiError` detail,
login token storage, and the 401 → refresh → replay path) plus the Design, Retro, SAR and
Tools screens; Composer, Library, Docking and Settings have no tests yet, and neither
does any file in `src/components/`. The repo-root `make test` runs pytest only and does
**not** run these — `pnpm test` from `apps/desktop/` is the only way to run them.

## Layout

```
src/
  theme/        tokens.css (the Twitter Dim palette) + global.css primitives
  lib/api.ts    typed FastAPI client — health, auth (login/tenants + silent 401
                refresh & replay), projects, libraries + import/export, tools,
                settings, molecules (profile/assess/conformer), docking,
                agent WS streams (design/chat), run export
  lib/rdkit.ts  lazy single-flight loader for the RDKit-JS WASM module
  lib/mol3d.ts  lazy loader for the 3Dmol.js viewer bundle
  hooks/useRDKit.ts   React hook exposing the RDKit module when ready
  components/   Sidebar, TopBar (health pill), CommandPalette (⌘K), MoleculeInspector,
                MoleculeStructure (RDKit 2D SVG), MoleculeDepiction (2D/3D toggle),
                Molecule3D + DockingPose3D (3Dmol.js), KetcherEditor + MoleculeEditorModal
  screens/      ComposerScreen (chat-driven design), DesignScreen (one-shot loop),
                LibraryScreen (projects + I/O), DockingScreen, RetroScreen, SarScreen,
                ToolsScreen (registry playground), SettingsScreen (sign-in + BYO-LLM),
                MoleculeCard, LibraryMoleculeCard, SaveToLibraryModal, ContextPickerModal
  test/         vitest setup (jest-dom matchers + a jsdom localStorage shim)
src-tauri/      the Rust shell (window config, icons, capabilities)
```

## What works now

The **Composer** is the app's front door and the screen it opens on: a multi-turn chat
over `WS /agent/chat/stream`. Each turn is either a design run — analogs stream in as
cards, ranked as they arrive — or a conversational reply; a working seed SMILES carries
across turns so follow-ups ("now lower logP") build on the last structure, molecules can
be `@`-attached as context or drawn with **✎ Draw**, candidates can be multi-selected and
saved to a library, and each design turn offers one-click **⬇ notebook / ⬇ report** export
of that run.

The **Design** screen drives the backend's agentic design loop end-to-end over
`WS /agent/design/stream`: enter a natural-language goal + a seed SMILES, run it, and
watch the plan, candidate molecules, execution trace, ranking and explanation stream in
live. Candidates render as they arrive and re-sort on the `ranked` event; the terminal
`complete` frame supplies the authoritative final set. Each candidate shows a **2D
structure depiction** (rendered client-side by RDKit-JS), property chips and pass/fail —
plus one-click notebook/report export of the run.

The **Library** screen manages projects and libraries against the I/O endpoints: pick or
create a project, create libraries, **import** molecules by pasting SMILES / CSV / SDF
(firewalled + InChIKey-deduped server-side; invalid rows reported, not fatal), browse them
as cards with 2D structures and property chips (imported CSV columns included), and
**export** the set as SMILES / CSV / SDF.

The **Tools** screen is a playground over the typed tool registry (`GET /tools`): browse
every tool the backend registers, grouped by category (22 built-ins today, plus any opt-in
container tools — the TopBar health pill shows the live count from `GET /health`), pick
one to get a **form generated from its JSON-schema parameters** (string / number / array
inputs, with sensible prefills), run it (`POST /tools/{name}`, optional seed), and see the
provenance (compute class, duration, cache hit, determinism), any structures in the output
rendered 2D, and the raw JSON. Adapter-gated tools (ADMET/docking) surface their "not
configured" error cleanly.

The **Docking** screen posts to the adapter-gated `dock` tool (`POST /tools/dock`) with a
ligand SMILES, a receptor `.pdbqt` path and a pocket center/size, renders the returned
poses table (mode, affinity, RMSD l.b./u.b., geometry), and turns a 501 into a clean
"Docking engine not configured" notice rather than a fabricated result. It also ships a
3Dmol.js pose viewer: **Load sample complex (1HSG)** pulls the bundled RCSB HIV-1 protease
+ indinavir structure from `GET /examples/docking/sample` (experimental crystallographic
data shipped as a sample — not a Glowsky-computed pose).

The **Retrosynthesis** screen is a focused view over the `retrosynthesize` tool: each
one-step, template-based disconnection renders as target ⇒ precursors with RDKit 2D
depictions, a named-reaction chip, and a "building blocks" badge for routes whose
precursors all look purchasable.

The **Matched Pairs & SAR** screen runs `sar_transforms` and `matched_pairs` in parallel
over a pasted molecule set (one SMILES per line) and tabulates the support-ranked
transformations (n, mean/median/min/max Δ) plus the underlying matched pairs, for any of
11 properties (logP, MW, TPSA, HBD, HBA, rotatable bonds, aromatic rings, Fsp3, QED,
heavy atoms, MPO).

Everywhere: **⌘/Ctrl+K** opens a command palette — navigation plus one-line molecule
actions that compose a Composer turn (seed + prefilled prompt) rather than computing
separately — and the **🔬** button on any molecule card opens the **Molecule Inspector**:
MPO desirability bars with the limiting axis called out, a synthesizability verdict with a
one-step route, the 7-rule drug-likeness battery, and PAINS/BRENK structural alerts, via
`POST /molecules/assess`.

The **Settings** screen is where you sign in: **Platform access** takes your
nakitte-carbon-auth email + password (proxied through the backend to `POST /auth/login`;
the password is never stored and the session refreshes silently), and when the returned
token isn't tenant-scoped it shows a workspace picker (`GET /auth/tenants` →
`POST /auth/select-tenant`) — or tells you to contact your admin if your account has no
tenant yet. Sign out clears the stored token, and an advanced "Paste a token directly"
escape hatch accepts a carbon-auth Bearer JWT. It also manages BYO-LLM: connect provider
keys (Anthropic / OpenAI / Groq / local) — encrypted server-side, shown only as a masked
hint and removable — and set the "provider/model" route for each task class (reasoning /
fast-triage / codegen), with an override/default badge and one-click revert. Stored
keys/routes drive the per-org gateway in the design loop.

### Rendering & editing stack

**2D depiction — RDKit-JS (offline).** Structures are drawn in-browser by the **RDKit
WebAssembly** build (`@rdkit/rdkit`) — no server round-trip, no CDN.
`scripts/copy-rdkit.mjs` stages the loader + `.wasm` (~6.9 MB) into `public/` on install /
before dev / before build; the module loads lazily and instantiates once
(`src/lib/rdkit.ts`) and the `.wasm` is served as a static asset — so the 6.9 MB never
enters a JS chunk. First paint pulls only the shell: a 219 KB entry chunk (67 KB gzipped)
plus 26 KB of CSS. The heavy editors are code-split behind dynamic imports and fetched on
demand — Ketcher (a 24 MB chunk plus ~1.6 MB of Indigo/Miew sub-chunks and 183 KB of CSS)
and 3Dmol (593 KB). `dist/` totals ~33 MB, essentially all of it lazily loaded. Each
`MoleculeStructure` validates the SMILES and frees the WASM-side molecule after drawing.
Depictions are drawn for **dark mode** — a transparent background with a light atom
palette (light carbon → light bonds, lightened heteroatoms) so they read on the Dim
surface (`DARK_DRAW_OPTIONS` in `MoleculeStructure.tsx`).

**2D editing — Ketcher 3.15.0 (offline).** `MoleculeEditorModal` `React.lazy`-loads
`KetcherEditor`, which mounts `ketcher-react`'s `<Editor>` against a module-level
`new StandaloneStructServiceProvider()` — the Indigo engine runs in a Web Worker, so
drawing, cleanup, and SMILES export need no backend and no network. Reachable from the
✎ Draw buttons on the Composer and Design screens and from the command palette's "Draw /
edit a molecule". Ketcher is authored for a webpack/CRA world, which is why
`vite.config.ts` carries the `vite-plugin-node-polyfills` globals shim, the
`process.env.NODE_DEBUG` define, `build.commonjsOptions.transformMixedEsModules`, and
`optimizeDeps.include` for the three ketcher packages.

**3D — 3Dmol.js 2.5.5.** `src/lib/mol3d.ts` dynamically imports
`3dmol/build/3Dmol.es6.js` on first use and caches the promise. `Molecule3D` fetches an
MMFF-minimized conformer from the backend (`POST /molecules/conformer`) and renders it
stick+sphere behind `MoleculeDepiction`'s 2D/3D toggle (defaults to 2D). `DockingPose3D`
draws the receptor as a spectrum cartoon plus a translucent VDW surface with the ligand in
stick/sphere, wired to the Docking screen's sample-complex viewer.

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
