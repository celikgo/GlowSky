---
name: updating-design-tokens
description: Use when changing anything colour-related in the desktop app — apps/desktop/src/theme/tokens.css, a new theme, a new token, a contrast fix, or a component that needs a colour it does not have. Covers the token contract, semantic naming, the define-in-every-theme rule, contrast verification, and the element-colour exemption. Triggers on "design tokens", "tokens.css", "theme", "dark mode", "light theme", "lights out", "palette", "colour", "color", "contrast", "WCAG", "accessibility", "the light theme looks wrong".
---

# Updating design tokens

`apps/desktop/src/theme/tokens.css` is the only place the desktop app names a
colour, with one exception (§5). Changing it touches every screen and every
screenshot. This skill is the contract those changes hold to.

Everything below is enforced by `scripts/check_design_tokens.py` in the
`design-tokens` job of `.github/workflows/ci.yml`. Nothing in this file is
advisory. Run it locally with `make tokens`.

## When to use this skill

- Adding or changing a token value.
- Adding a theme.
- A component needs a colour and no existing token fits.
- Fixing a contrast problem, or answering "is this readable in the light theme?"

## When NOT to use this skill

- Adding a one-off colour for one component. That is the thing tokens exist to
  prevent — use an existing token, or add one through this skill.
- Changing an **element** colour. That is `rendering-molecules`, and the answer
  is almost always no.

## The contract

1. **Every colour comes from a token.** A raw `#15202b`, `rgba(...)`,
   `hsl(...)` or `0x1e2732` anywhere under `apps/desktop/src` outside
   `theme/tokens.css` and `theme/cpk.ts` fails CI. The count is held under
   `TOKEN_LINT_CEILING`, which **only goes down**: the check fails if you go
   above it, and it also fails if you go below it without lowering the ceiling
   in the same change. Slack left in a ceiling is where the next one hides.
2. **Every colour token is defined in every theme**, even when the value
   repeats. A token in `dim` and not in `light` does not fall back to anything
   sensible. Non-colour tokens (radii, fonts, layout) live in the shared
   `:root` block; a *colour* in that block fails, because it would escape rule 2.
3. **Every contrast pair the app paints clears its floor.** 4.5:1 for text
   (WCAG 1.4.3 AA), 3:1 for control boundaries and graphics (1.4.11). The pairs
   are declared in `CONTRAST_OBLIGATIONS`; if you paint a token on a ground that
   is not in that list, add it.
4. **A ratio you write in a comment must be true.** The form is fixed so it can
   be checked: `N.NN:1 on --some-token`. A bare `4.5:1` with no ground named is
   an error, not something skipped — an unfalsifiable claim is the thing this
   repository does not ship.
5. **A `var(--x)` must name a token something defines.** `--text-primary` was
   read twice in `global.css` and defined nowhere; it silently resolved to its
   fallback and put two different whites on screen for a release.

## Adding a token

1. **Justify it in the PR body.** Why does no existing token cover this? If the
   answer is thin, you want an existing token.
2. **Name it for its purpose, not its appearance.** `--danger`, not `--red`.
   `--bg-elevated`, not `--gray-2`. No numeric scales — a name that describes
   the job survives a palette swap; `--blue-500` does not.
3. **Define it in `dim`, `light` AND `lights-out`.** Write the value out in each
   even when it repeats. CI fails otherwise.
4. **Work out where it will be painted, and add those pairs to
   `CONTRAST_OBLIGATIONS`.** A token nobody measures is a token that will fail
   in the light theme first and be noticed in a screenshot second.
5. **Run `make tokens`.** It prints every ratio it computed, so read the output
   rather than only its exit code.
6. **Add a row to `docs/14-design-system.md` §3** if it carries a contrast
   obligation.

## Adding a theme

1. Add the name to `THEMES` in `src/theme/theme.ts` and a label to
   `THEME_LABELS`. CI fails if the switcher offers a theme `tokens.css` has no
   block for.
2. Define **every** token that exists in the other themes.
3. `--mol-canvas`, `--mol-label` and `--viewer-canvas` must be **identical** to
   the other themes. They are the grounds element colours are measured against;
   see `rendering-molecules`, and expect CI to tell you so.
4. Set `color-scheme` in the block so the UA paints form controls and scrollbar
   gutters to match.
5. `make tokens`, then read every ratio for the new theme.

## Fixing a contrast failure

The check names the pair, the measured ratio and the floor. In order of
preference:

1. **Move the foreground**, usually one step darker on a light ground or one
   lighter on a dark one. Then update the ratio in the comment — CI will tell
   you if you get it wrong.
2. **Move the ground.** Legitimate when one surface is the outlier — the dim
   `--bg-input` was lighter than the card it sat in, which is what pushed
   placeholder text to 2.50:1.
3. **Change what the token is for.** `--text-tertiary` could not clear 4.5:1 in
   any dark theme against every ground it landed on, so it stopped being a text
   colour and the two places that used it as one moved to `--text-secondary`.
4. **Never** relax the floor, and never leave a ratio in a comment that the
   code no longer measures.

## The element-colour exemption

`apps/desktop/src/theme/cpk.ts` is the second file allowed a colour literal.
Element colours are chemical identity — a chemist reads red as oxygen — so they
are not tokens, are not re-tinted by a theme, and are exempt from rule 1. They
are **not** exempt from measurement: the check computes every one of them
against `--mol-canvas`, and four are published as below the floor rather than
adjusted. Read `rendering-molecules` before touching that file.

The practical consequence for this skill: **you cannot theme a molecule ground.**
If a change wants `--mol-canvas` dark in the dim theme, the answer is no, and
`cpk.ts` carries the measurement saying why.

## Common mistakes

- **Adding a colour to a component "just for this one case."** That is how the
  six hand-inlined `rgba()` tints got in — each one a semantic colour
  re-derived by hand, so a palette change moved the chip's text and left its
  background behind.
- **Defining a token in `dim` and assuming the rest inherit.** They do not.
- **Writing `var(--danger, #f4212e)`.** The fallback is inert while the token
  exists, and hard-codes today's palette at the call site for when it does not.
- **Quoting a ratio you did not compute.** `make tokens` computes them.
- **Using `--text-tertiary` for text.** It is decoration; it does not clear AA.
- **Putting a colour in the shared `:root` block** because it is the same in
  every theme. Say it three times; that is the rule that makes theme drift
  impossible.
- **Re-tinting an element colour so it reads better on a dark card.** That is
  the exact bug this system replaced.

## Checklist

- [ ] Token defined in `dim`, `light` and `lights-out`.
- [ ] Named for purpose, not appearance.
- [ ] Every ground it is painted on is in `CONTRAST_OBLIGATIONS`.
- [ ] Every ratio in a comment is `N.NN:1 on --token` and is what it measures.
- [ ] `make tokens` passes, and you read its output.
- [ ] `TOKEN_LINT_CEILING` lowered if you removed a literal.
- [ ] `docs/14-design-system.md` updated if a contrast obligation changed.
- [ ] PR body says *why*; the diff already says what.

## Reference

- `apps/desktop/src/theme/tokens.css` — the palette and the argument for each value.
- `apps/desktop/src/theme/cpk.ts` — element colours; the exemption.
- `apps/desktop/src/theme/theme.ts` — theme names, storage, resolution.
- `scripts/check_design_tokens.py` — the gate; `CONTRAST_OBLIGATIONS` and
  `TOKEN_LINT_CEILING` are the two things you will edit.
- `tests/test_design_tokens.py` — the gate's own tests.
- `docs/14-design-system.md` — the measured tables.
- There is **no Storybook and no visual-regression suite.** Contrast is checked
  arithmetically; how a screen *looks* in a new theme is checked by opening it
  (`make desktop`).
