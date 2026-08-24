# Design System

> **Status legend.** ✅ shipped · 🟡 partial · ⏳ planned. Everything on this page
> is ✅ shipped unless a marker says otherwise, and every number on it is
> recomputed by `.github/workflows/ci.yml` on every push — see §6.

The desktop app's visual contract. It exists for the same reason
`VALIDATION.md` exists: a claim that nothing checks stops
being true without anybody noticing. The contrast ratios below are not design
intent, they are measurements, and `scripts/check_design_tokens.py` recomputes
each one from the shipped stylesheet.

---

## 1. The contract

Three rules, all enforced:

1. **Every colour in `apps/desktop/src` comes from a token.** A raw `#15202b`,
   `rgba(...)`, `hsl(...)` or `0x1e2732` outside `src/theme/tokens.css` and
   `src/theme/cpk.ts` fails CI, under a committed ceiling that only goes down.
2. **Every colour token is defined in every theme.** A token present in `dim`
   and missing from `light` does not fall back to something sensible.
3. **Every contrast pair the app actually paints clears its WCAG floor**, and
   every ratio quoted in a comment recomputes to the value it states.

The `0x` form is in the list because it already shipped: `lib/mol3d.ts` carried
`export const SURFACE = 0x1e2732`, a hand-copied duplicate of `--bg-elevated`
that a `#`-shaped grep would never have found.

## 2. Themes

| theme | when | ground |
|---|---|---|
| `dim` | default | X's blue-tinted dark, `#15202b` |
| `light` | printing, projecting, screenshotting a structure | `#ffffff` |
| `lights-out` | OLED panels | `#000000` |

Selected by a `data-theme` attribute, stored under `glowsky.theme`, and applied
by an inline script in `index.html` **before first paint** — applying it from
React means one frame of the wrong theme on every launch. That script is a
hand-inlined copy of `readChoice` + `resolveTheme`;
`src/theme/theme.test.ts` parses `index.html` and asserts the copy still agrees.

A fourth choice, `system`, follows `prefers-color-scheme`. It resolves a dark
preference to **`dim`, never `lights-out`** — pure black is a panel-specific
choice a user makes, not one to infer from an OS setting.

The blocks are scoped to `[data-theme="…"]` rather than `:root[data-theme="…"]`,
so any subtree can opt into another theme. The Settings switcher uses that to
preview each theme with that theme's real tokens instead of a copied swatch.

**Where the values come from.** blaeu-lib's
`packages/core/src/theme/themes/twitter.ts`, which reproduces X's three schemes
with the contrast corrections X's own values need. It is cited rather than
re-derived, the way this repository cites a paper rather than restating a model.
Three of its corrections apply directly, and two more were needed because this
app paints text on surfaces a map library does not have — both are marked
*(this repo)* in §3.

## 3. Measured contrast

Every pair below is one the app actually paints. `4.5:1` is WCAG 2.1 SC 1.4.3
(AA body text); `3:1` is SC 1.4.11 (graphical objects and control boundaries).
Ratios against a `--*-subtle` token are measured on that tint composited over
`--bg-elevated`, because that is where those chips and caveats are drawn.

| pair | floor | dim | light | lights-out |
|---|---|---|---|---|
| `--text` on `--bg` | 4.5 | 15.61 | 18.51 | 17.24 |
| `--text-secondary` on `--bg-elevated-2` | 4.5 | 4.58 | 5.48 | 4.74 |
| `--accent` on `--bg-elevated` | 4.5 | 5.03 | 5.24 | 5.92 |
| `--text-on-accent` on `--accent-strong` | 4.5 | 4.67 | 4.67 | 4.67 |
| `--success` on `--success-subtle` | 4.5 | 4.93 | 5.15 | 5.90 |
| `--warning` on `--warning-subtle` | 4.5 | 7.51 | 4.66 | 8.97 |
| `--danger` on `--danger-subtle` | 4.5 | 4.60 | 4.55 | 5.44 |
| `--border-control` on `--bg-elevated` | 3.0 | 3.68 | 3.32 | 3.12 |
| `--text-tertiary` on `--bg` | 3.0 | 3.21 | 3.51 | 3.43 |

Five corrections were needed to get there, and each replaced something that was
shipping:

- **`--accent-strong` (blaeu-lib).** A filled button was `--accent` `#1d9bf0`
  with a white label: **3.00:1**, X's most-cited contrast failure and below AA.
  Buttons now take `#1578c2` (4.67:1). The vivid blue stays as the link and mark
  colour, where 3:1 is the applicable floor, and as `--brand-from`.
- **`--danger` in the dark themes (blaeu-lib).** X's `#f4212e` measures 3.67:1
  on `--bg-elevated` and is used as *text* — chips, and the out-of-domain
  caveat. Now `#f87171` (5.46:1).
- **`--warning` in the light theme (blaeu-lib).** X's `#ffd400` on white is
  1.43:1. Now `#965900`.
- **The light semantic trio *(this repo)*.** blaeu-lib's light values clear AA
  against the surface (5.08 / 4.66 / 4.75) but this app also paints them on
  their own 10% tint, where they measured 4.42 / 4.10 / 4.06. Darkened one step
  until they clear on the tint too.
- **`--text-tertiary` is no longer a text colour *(this repo)*.** In dim it
  measured **2.50:1** against `--bg-input`, and it was the colour of the input
  placeholder and of `.prediction__prov` — the line naming which model produced
  a number. Both now use `--text-secondary`. `--text-tertiary` survives for
  decoration (status dots, rules) under the 3:1 floor.

Two further defects were fixed on the way: `--text-primary` was read twice in
`global.css` and defined nowhere, so prediction labels and values shipped at
`#e7e9ea` while the rest of the app used `#f7f9f9`; and `--radius-md` was read
and undefined, pinning `.prediction`'s corner radius to its fallback.

## 4. Molecules do not follow the theme

Atom colour is chemical identity. Oxygen is red, nitrogen is blue, sulfur is
yellow, and a molecule that changes colour when the app changes colour is a
molecule saying something different. `src/theme/cpk.ts` holds the element
tables and is the only file besides `tokens.css` allowed a colour literal.

Before this, `MoleculeStructure.tsx` carried a `DARK_DRAW_OPTIONS` constant in
which oxygen was `#ff7373` and nitrogen `#6ba3ff` — CPK hues lightened to read
well on the Dim surface. That is exactly the failure this rule names.

**The measurement that decides the design.** No published element palette is
legible on both a light and a dark ground:

| palette | on white | on `#15202b` |
|---|---|---|
| Jmol / CPK (screen) | H **1.00**, S **1.07**, Cl **1.55** | worst 2.11 |
| RDKit 2D (print) | worst 1.72 | C/H **1.27**, N **1.92** |

So the **ground** is what stays fixed. `--mol-canvas` and `--viewer-canvas` are
identical in all three themes, each pinned to the ground its palette is defined
against, and `scripts/check_design_tokens.py` fails if a theme moves either.
Everything around a drawing — card, border, legend, placeholder, loading state
— themes normally. This also matches what the app already did for Ketcher,
whose canvas was pinned light with the comment *"Ketcher's drawing surface is
light by design."*

Both tables are read out of RDKit 2026.03.5's own shipped palettes
(`useAvalonAtomPalette()` and `useCDKAtomPalette()`), not transcribed.

**Nothing ships below the 3:1 floor.** `CPK_2D` is RDKit's **Avalon** palette
rather than its default, and that is a deliberate trade rather than a free win.
The default is the familiar one — yellow sulfur, cyan fluorine, green chlorine —
and four of its colours are illegible on white: sulfur 1.72:1, fluorine 1.97:1,
chlorine 2.16:1, phosphorus 2.52:1. Avalon clears the floor for every element:

| element | on `--mol-canvas` | | element | on `--mol-canvas` |
|---|---|---|---|---|
| C / H / default | 21.00:1 | | P | 9.51:1 |
| N | 8.59:1 | | S | 8.04:1 |
| O | **4.00:1** (worst) | | Cl | 5.20:1 |
| F | 5.20:1 | | Br | 5.20:1 |
| I | 13.84:1 | | | |

**What it costs, measured.** Avalon buys contrast by spending hue:

| pair | CIE76 dE | |
|---|---|---|
| F / Cl / Br | **0.0** | byte-identical `#007F00` |
| P vs I | 23.5 | both purple |

So colour no longer separates one halogen from another, and sulfur is brown
rather than the yellow a chemist expects. Element identity is not lost — a 2D
depiction draws the atom **symbol** as well, so an F is labelled F, and colour is
a redundant second channel. This palette trades some of that redundancy for a
legible first one. It is an owner decision, recorded rather than presented as
self-evident.

Both failure modes are gated, so neither can quietly get worse.
`CPK_2D_BELOW_FLOOR` is **empty**, and emptiness is the mechanism working rather
than the absence of one: an element added below 3:1 fails until somebody writes
down its number. `CPK_2D_INDISTINGUISHABLE` lists the four collisions above with
their measured dE, so a *fourth* element joining the green pile fails a build,
a published collision getting closer fails, and an entry that stops being true
must be removed.

### The 3D table

`CPK_3D` — the Jmol table, on `--viewer-canvas` — is gated the same way, with
the opposite result: **no collisions, and two elements below the floor that
stay there.**

| | |
|---|---|
| bromine | 2.68:1 |
| iodine | 2.42:1 |

There is nowhere to move them. A sweep of every grey ground puts the best
achievable worst-case at **2.69:1, at pure black** — so no ground clears this
table, and pure black would buy 0.27 while costing a black rectangle inside a
themed card. The one alternative 3Dmol ships, its `rasmol` table, still fails
bromine (2.67:1) *and* introduces five collisions including boron and chlorine
at the same green.

That trade is worse here than the equivalent one was in 2D, and the reason is
worth stating: **a 3D scene draws no atom labels.** In the 2D depiction colour
is a redundant second channel next to the atom symbol, which is what made
Avalon's halogen collision acceptable. In 3D colour is the *only* identity
channel, so a collision loses the information rather than making it harder to
read. `CPK_3D_INDISTINGUISHABLE` is empty and must stay that way.

The 3:1 floor is applied to 3D as a **conservative proxy**, not because WCAG
1.4.11 is in scope. A 3D atom is a lit sphere with a specular highlight and
depth cues, so its rendered pixels span a range around the base colour and a
flat base-vs-ground ratio understates what a viewer can see. Holding it to the
flat-graphics standard anyway makes these two numbers an upper bound on the
problem rather than a description of it.

## 5. What the app does not encode in colour

Worth stating, because a reader of §3 may assume more is colour-coded than is:

- **There is no docking-score legend and no score-to-colour mapping.** In
  `DockingScreen` the affinity is plain text in a plain table. That is
  deliberate and this page is not proposing to change it — a colour ramp over a
  Vina score would imply a calibration that does not exist.
- **Numeric properties are uncoloured.** `MW`, `logP`, `TPSA`, `QED` are neutral
  chips with no thresholding.
- **The one value-to-colour encoding is the sign of a delta**, in `SarScreen`:
  `datatable__pos` / `datatable__neg` on the mean Δ column. 🟡 It encodes
  *sign*, not *desirability* — a negative Δ logP renders in `--danger` red
  although lower logP is usually the wanted direction, and there is no legend
  saying so. Recorded here rather than quietly fixed, because changing it is a
  product decision about what the colour should mean.

## 6. What CI enforces

`.github/workflows/ci.yml`, job `design-tokens`, running
`python -m scripts.check_design_tokens` — stdlib only, no install step. It will
not let you merge:

| # | check |
|---|---|
| 1 | a raw colour literal under `apps/desktop/src` outside the palette and the element table, above the committed ceiling |
| 1b | a `var(--token)` naming something nothing defines |
| 2 | a token defined in one theme and missing from another; a colour in the shared `:root` block; a theme offered in the switcher with no block; a theme that moves a molecule ground |
| 3 | a text or control pair below its WCAG floor; an element colour in **either** palette below the floor that is not published as such; two elements closer than dE 25 that are not published as such; a published shortfall or collision getting worse; a published entry naming an element the palette no longer defines |
| 4 | a contrast ratio written in a `tokens.css` comment that is not what that colour measures |

`tests/test_design_tokens.py` runs the same checker against inputs that should
fail it, so the failure path is exercised rather than assumed.

Run it locally with `make tokens`.

## 7. Reference

- `apps/desktop/src/theme/tokens.css` — the palette, and the argument for each value.
- `apps/desktop/src/theme/cpk.ts` — element colours and the grounds they are defined against.
- `apps/desktop/src/theme/theme.ts` — theme names, storage, resolution.
- `scripts/check_design_tokens.py` — the gate.
- `.claude/skills/updating-design-tokens` and `.claude/skills/rendering-molecules`.
- `10-tech-stack.md` — where the frontend stack is recorded.
