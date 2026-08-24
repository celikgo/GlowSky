"""Enforce the desktop app's design-token contract.

Three checks, all of which read the real files rather than a copy of them, so
this script cannot drift from what ships:

  1. NO RAW COLOUR LITERALS outside the two files entitled to hold one.
     `apps/desktop/src/theme/tokens.css` defines the palette; the element-colour
     table in `apps/desktop/src/theme/cpk.ts` is chemical data rather than
     design (see that file's header). Everything else must reach a colour
     through `var(--token)`. Existing violations are held under a committed
     ceiling that can only go down — see TOKEN_LINT_CEILING.

  2. THEME PARITY. Every colour token defined in one `[data-theme]` block must
     be defined in all of them. A token present in `dim` but missing from
     `light` does not fall back to something sensible; it falls back to whatever
     the browser last computed, which is how a light theme ends up with a dark
     chip nobody notices for a release.

  3. CONTRAST. Every pair in CONTRAST_OBLIGATIONS is computed from the values
     actually in tokens.css and checked against its WCAG floor, in every theme.
     The element colours are checked against the surfaces they are drawn on.
     This is the check that makes the accessibility claims in
     `docs/14-design-system.md` and `.claude/skills/updating-design-tokens`
     statements about the code rather than about our intentions.

Run:  python -m scripts.check_design_tokens        (or scripts/check_design_tokens.py)
Exit: 0 clean, 1 on any violation.
"""

from __future__ import annotations

import math
import re
import sys
from dataclasses import dataclass
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SRC = REPO / "apps" / "desktop" / "src"
TOKENS_CSS = SRC / "theme" / "tokens.css"
CPK_TS = SRC / "theme" / "cpk.ts"
THEME_TS = SRC / "theme" / "theme.ts"

# The two files entitled to hold a raw colour literal, and why. Anything else
# that names a colour directly is a violation.
COLOUR_LITERAL_EXEMPT = {
    TOKENS_CSS: "defines the palette; this is where colour literals live",
    CPK_TS: "element identity colours — chemical data, not design (see the file header)",
}

# Existing raw-colour-literal violations, held under a ratchet. This number may
# only ever go DOWN: the check fails if the count exceeds it, and also fails if
# the count is below it, which forces the ceiling down with the fix rather than
# leaving slack for the next one to hide in.
TOKEN_LINT_CEILING = 0

# ---------------------------------------------------------------------------
# WCAG 2.1 relative luminance and contrast.
# ---------------------------------------------------------------------------


def _srgb_to_linear(channel: float) -> float:
    c = channel / 255.0
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def relative_luminance(rgb: tuple[float, float, float]) -> float:
    r, g, b = (_srgb_to_linear(c) for c in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast_ratio(
    fg: tuple[float, float, float], bg: tuple[float, float, float]
) -> float:
    lf, lb = relative_luminance(fg), relative_luminance(bg)
    lighter, darker = max(lf, lb), min(lf, lb)
    return (lighter + 0.05) / (darker + 0.05)


def composite(
    fg: tuple[float, float, float, float], bg: tuple[float, float, float]
) -> tuple[float, float, float]:
    """Flatten a translucent foreground onto an opaque ground (source-over)."""
    r, g, b, a = fg
    return (
        r * a + bg[0] * (1 - a),
        g * a + bg[1] * (1 - a),
        b * a + bg[2] * (1 - a),
    )


def _to_lab(rgb: tuple[float, float, float]) -> tuple[float, float, float]:
    """sRGB -> CIE L*a*b* (D65), so two element colours can be compared the way
    an eye compares them rather than the way a hex string compares."""
    r, g, b = (_srgb_to_linear(c) for c in rgb)
    x = (r * 0.4124 + g * 0.3576 + b * 0.1805) / 0.95047
    y = r * 0.2126 + g * 0.7152 + b * 0.0722
    z = (r * 0.0193 + g * 0.1192 + b * 0.9505) / 1.08883

    def f(t: float) -> float:
        return t ** (1 / 3) if t > 0.008856 else 7.787 * t + 16 / 116

    fx, fy, fz = f(x), f(y), f(z)
    return (116 * fy - 16, 500 * (fx - fy), 200 * (fy - fz))


def delta_e(a: tuple[float, float, float], b: tuple[float, float, float]) -> float:
    """CIE76 colour difference. Roughly: under ~2.3 is imperceptible, under ~25
    is 'the same colour family' to someone scanning rather than comparing."""
    la, lb = _to_lab(a), _to_lab(b)
    return math.sqrt(sum((x - y) ** 2 for x, y in zip(la, lb, strict=True)))


_HEX_RE = re.compile(r"^#([0-9a-fA-F]{3,8})$")
_FUNC_RE = re.compile(r"^rgba?\(([^)]*)\)$", re.IGNORECASE)


def parse_colour(value: str) -> tuple[float, float, float, float] | None:
    """Parse a CSS colour into (r, g, b, alpha). None if it is not a colour."""
    value = value.strip()
    named = {"white": "#ffffff", "black": "#000000"}
    value = named.get(value.lower(), value)

    m = _HEX_RE.match(value)
    if m:
        h = m.group(1)
        if len(h) in (3, 4):
            h = "".join(ch * 2 for ch in h)
        if len(h) not in (6, 8):
            return None
        r, g, b = (int(h[i : i + 2], 16) for i in (0, 2, 4))
        a = int(h[6:8], 16) / 255.0 if len(h) == 8 else 1.0
        return (float(r), float(g), float(b), a)

    m = _FUNC_RE.match(value)
    if m:
        parts = [p.strip() for p in m.group(1).replace("/", " ").split(",")]
        if len(parts) == 1:
            parts = m.group(1).split()
        if len(parts) < 3:
            return None
        try:
            fr, fg, fb = (float(p.rstrip("%")) for p in parts[:3])
        except ValueError:
            return None
        alpha = 1.0
        if len(parts) >= 4:
            raw = parts[3].strip()
            alpha = float(raw.rstrip("%")) / (100.0 if raw.endswith("%") else 1.0)
        return (fr, fg, fb, alpha)

    return None


# ---------------------------------------------------------------------------
# Parsing. Both sources are read from disk so this file cannot hold a stale
# copy of a value it claims to be checking.
# ---------------------------------------------------------------------------

_COMMENT_RE = re.compile(r"/\*.*?\*/", re.DOTALL)
_LINE_COMMENT_RE = re.compile(r"(?<![:\"'])//[^\n]*")
_BLOCK_RE = re.compile(
    r"(?::root|\[data-theme=\"(?P<theme>[a-z-]+)\"\])\s*\{(?P<body>[^}]*)\}"
)
_DECL_RE = re.compile(r"(--[a-z0-9-]+)\s*:\s*([^;]+);")


def _blank(match: re.Match[str]) -> str:
    """Replace a comment with the same number of newlines, so that stripping
    comments never shifts a reported line number off the line it names."""
    return "\n" * match.group(0).count("\n")


def strip_css_comments(text: str) -> str:
    return _COMMENT_RE.sub(_blank, text)


def strip_ts_comments(text: str) -> str:
    return _LINE_COMMENT_RE.sub("", _COMMENT_RE.sub(_blank, text))


def parse_tokens_css(text: str) -> dict[str, dict[str, str]]:
    """`{theme -> {token -> value}}`. The bare `:root` block is keyed `""`."""
    blocks: dict[str, dict[str, str]] = {}
    for m in _BLOCK_RE.finditer(strip_css_comments(text)):
        theme = m.group("theme") or ""
        decls = blocks.setdefault(theme, {})
        for name, value in _DECL_RE.findall(m.group("body")):
            decls[name] = " ".join(value.split())
    return blocks


_TS_GROUND_RE = re.compile(
    r"export const (?P<name>MOL_CANVAS|MOL_LABEL|VIEWER_CANVAS)\s*=\s*\"(?P<hex>#[0-9a-fA-F]{6})\""
)

# The ground constant in cpk.ts, and the token it must equal.
GROUND_PAIRS = (
    ("MOL_CANVAS", "--mol-canvas"),
    ("MOL_LABEL", "--mol-label"),
    ("VIEWER_CANVAS", "--viewer-canvas"),
)

_TS_OBJ_RE = re.compile(
    r"export const (?P<name>CPK_2D|CPK_3D)\b[^=]*=\s*Object\.freeze\(\{(?P<body>[^}]*)\}"
)
_TS_ENTRY_RE = re.compile(r"\"?([A-Za-z0-9_-]+)\"?\s*:\s*\"(#[0-9a-fA-F]{6})\"")


def parse_cpk_ts(text: str) -> dict[str, dict[str, str]]:
    """`{"CPK_2D": {element -> hex}, "CPK_3D": {...}}`."""
    out: dict[str, dict[str, str]] = {}
    for m in _TS_OBJ_RE.finditer(strip_ts_comments(text)):
        out[m.group("name")] = dict(_TS_ENTRY_RE.findall(m.group("body")))
    return out


_THEMES_TS_RE = re.compile(r"export const THEMES = \[(?P<body>[^\]]*)\] as const")


def parse_declared_themes(text: str) -> list[str]:
    """The theme names `theme.ts` offers in the switcher. tokens.css must define
    a block for each — a theme the UI offers and the stylesheet does not define
    is a menu entry that changes nothing."""
    m = _THEMES_TS_RE.search(strip_ts_comments(text))
    return re.findall(r"\"([a-z-]+)\"", m.group("body")) if m else []


def parse_cpk_grounds(text: str) -> dict[str, str]:
    """`{"MOL_CANVAS": "#FFFFFF", ...}` from cpk.ts."""
    return {m.group("name"): m.group("hex") for m in _TS_GROUND_RE.finditer(strip_ts_comments(text))}


def resolve(value: str, decls: dict[str, str], seen: frozenset[str] = frozenset()) -> str:
    """Follow `var(--x)` (and its fallback) until a literal colour is reached."""
    value = value.strip()
    m = re.fullmatch(r"var\(\s*(--[a-z0-9-]+)\s*(?:,\s*(.+))?\)", value)
    if not m:
        return value
    name, fallback = m.group(1), m.group(2)
    if name in seen:
        return fallback or value
    if name in decls:
        return resolve(decls[name], decls, seen | {name})
    return resolve(fallback, decls, seen | {name}) if fallback else value


# ---------------------------------------------------------------------------
# Check 1 — no raw colour literals outside the two files entitled to one.
# ---------------------------------------------------------------------------

_LITERAL_RES = (
    # CSS/TS hex. `#root` and friends are not matched: `root` is not hex.
    re.compile(r"#[0-9a-fA-F]{3,8}\b"),
    re.compile(r"\brgba?\s*\(", re.IGNORECASE),
    re.compile(r"\bhsla?\s*\(", re.IGNORECASE),
    # `0x1e2732` — how a colour reaches a WebGL viewer, and invisible to a
    # `#`-only grep. This one already shipped once, in lib/mol3d.ts.
    re.compile(r"\b0x[0-9a-fA-F]{6}\b"),
)
_SCANNED_SUFFIXES = (".css", ".ts", ".tsx", ".html")


@dataclass(frozen=True)
class Violation:
    path: Path
    line: int
    text: str


def scan_colour_literals(root: Path) -> list[Violation]:
    """Every raw colour literal under `root`, ignoring comments and the two
    exempt files. Comments are stripped line-wise rather than by rewriting the
    file, so reported line numbers still point at the real line."""
    found: list[Violation] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.suffix not in _SCANNED_SUFFIXES:
            continue
        if path in COLOUR_LITERAL_EXEMPT:
            continue
        stripper = strip_css_comments if path.suffix == ".css" else strip_ts_comments
        text = path.read_text(encoding="utf-8")
        # Strip block comments across the whole file, then keep line structure.
        for lineno, line in enumerate(stripper(text).splitlines(), start=1):
            if any(pattern.search(line) for pattern in _LITERAL_RES):
                found.append(Violation(path, lineno, line.strip()))
    return found


# ---------------------------------------------------------------------------
# Check 1b — every token that is read is defined.
# ---------------------------------------------------------------------------

_VAR_READ_RE = re.compile(r"var\(\s*(--[a-z0-9-]+)")
# Ketcher ships its own ~109-property theme under a disjoint namespace and is
# styled by its own stylesheet, not by ours.
_FOREIGN_TOKEN_PREFIXES = ("--color-", "--ketcher-")


def scan_undefined_tokens(root: Path, defined: set[str]) -> list[Violation]:
    """A `var(--x)` naming a token nothing defines does not fail loudly; it
    falls through to the fallback, or to nothing. `--text-primary` shipped that
    way and put two different whites on screen beside each other."""
    found: list[Violation] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.suffix not in _SCANNED_SUFFIXES or path == TOKENS_CSS:
            continue
        stripper = strip_css_comments if path.suffix == ".css" else strip_ts_comments
        for lineno, line in enumerate(stripper(path.read_text(encoding="utf-8")).splitlines(), 1):
            for token in _VAR_READ_RE.findall(line):
                if token in defined or token.startswith(_FOREIGN_TOKEN_PREFIXES):
                    continue
                found.append(Violation(path, lineno, f"var({token}) is not defined in tokens.css"))
    return found


# ---------------------------------------------------------------------------
# Check 2 — theme parity.
# ---------------------------------------------------------------------------

# The grounds a molecule is drawn on. A theme is not allowed to move these:
# element colour is chemical identity, and no published element palette is
# legible on both a light and a dark ground (the numbers are in
# apps/desktop/src/theme/cpk.ts). Enforcing equality here is what makes "a
# theme change never alters a colour that encodes chemical meaning" a fact.
CHEMISTRY_GROUND_TOKENS = ("--mol-canvas", "--mol-label", "--viewer-canvas", "--viewer-surface")


def check_parity(
    themes: dict[str, dict[str, str]], grounds: dict[str, str], declared: list[str]
) -> list[str]:
    problems: list[str] = []
    named = {t: d for t, d in themes.items() if t}

    if not declared:
        problems.append(f"could not read THEMES out of {THEME_TS.name}")
    elif sorted(declared) != sorted(named):
        problems.append(
            f"{THEME_TS.name} offers {declared} but {TOKENS_CSS.name} defines "
            f"{sorted(named)} — a theme in the switcher with no block changes nothing"
        )
    if len(named) < 2:
        problems.append(
            f"expected at least two [data-theme] blocks in {TOKENS_CSS.name}, found {len(named)}"
        )
        return problems

    union: set[str] = set()
    for decls in named.values():
        union |= set(decls)
    for theme in sorted(named):
        missing = sorted(union - set(named[theme]))
        for token in missing:
            defined_in = sorted(t for t in named if token in named[t])
            problems.append(
                f"{token} is defined in {', '.join(defined_in)} but not in '{theme}' — "
                f"a token missing from a theme does not fall back to anything sensible"
            )

    # A colour token in the shared :root block would silently outrank nothing
    # and be invisible to the parity rule above.
    for token, value in themes.get("", {}).items():
        if parse_colour(value) is not None:
            problems.append(
                f"{token} = {value} is a colour in the shared :root block; "
                f"colours belong in the per-theme blocks so every theme states them"
            )

    for const, ground_token in GROUND_PAIRS:
        pinned = grounds.get(const)
        if pinned is None:
            problems.append(f"{CPK_TS.name} no longer exports {const}, which pins {ground_token}")
            continue
        for theme_name, decls in sorted(named.items()):
            actual = decls.get(ground_token)
            if actual is not None and actual.lower() != pinned.lower():
                problems.append(
                    f"[{theme_name}] {ground_token} is {actual} but {CPK_TS.name} pins it "
                    f"to {pinned} as {const}; the viewers paint that ground directly"
                )

    for token in CHEMISTRY_GROUND_TOKENS:
        values = {t: named[t].get(token) for t in sorted(named)}
        distinct = {v for v in values.values() if v is not None}
        if len(distinct) > 1:
            problems.append(
                f"{token} differs between themes ({values}) — it is a ground that "
                f"element colours are defined against and must not follow the theme; "
                f"see apps/desktop/src/theme/cpk.ts"
            )
    return problems


# ---------------------------------------------------------------------------
# Check 3 — contrast.
# ---------------------------------------------------------------------------

TEXT_FLOOR = 4.5  # WCAG 2.1 SC 1.4.3 (AA), body text
NONTEXT_FLOOR = 3.0  # WCAG 2.1 SC 1.4.11, graphical objects and control boundaries


@dataclass(frozen=True)
class Obligation:
    """One contrast pair the app actually paints, and the floor it must clear.

    `ground` is one token, or two — a translucent tint and the opaque surface
    it is composited over, which is how every `--*-subtle` chip背 is drawn.
    """

    fg: str
    ground: tuple[str, ...]
    floor: float
    where: str


CONTRAST_OBLIGATIONS: tuple[Obligation, ...] = (
    # Primary and muted text, on all four surfaces they land on.
    *(
        Obligation("--text", (bg,), TEXT_FLOOR, "body text")
        for bg in ("--bg", "--bg-elevated", "--bg-elevated-2", "--bg-input")
    ),
    *(
        Obligation("--text-secondary", (bg,), TEXT_FLOOR, "muted text, chips, placeholders")
        for bg in ("--bg", "--bg-elevated", "--bg-elevated-2", "--bg-input")
    ),
    # Links and accent text. `.prediction__cite` is a citation link on a card,
    # and a citation nobody can read is not provenance.
    Obligation("--accent", ("--bg",), TEXT_FLOOR, "links"),
    Obligation("--accent", ("--bg-elevated",), TEXT_FLOOR, "links on a card"),
    # The filled button. X's own #1D9BF0 with a white label is 3.00:1, which is
    # why --accent-strong exists; if that stops being true the button is wrong.
    *(
        Obligation("--text-on-accent", (bg,), TEXT_FLOOR, "filled-button label")
        for bg in ("--accent-strong", "--accent-strong-hover", "--accent-strong-pressed")
    ),
    # Semantic colours are painted as text both directly on a card (the SAR
    # delta columns) and on their own tint (chips, caveats).
    *(
        Obligation(fg, (bg,), TEXT_FLOOR, "semantic text on a card")
        for fg in ("--success", "--warning", "--danger")
        for bg in ("--bg-elevated",)
    ),
    *(
        Obligation(fg, (f"{fg}-subtle", "--bg-elevated"), TEXT_FLOOR, "chip / caveat text")
        for fg in ("--success", "--warning", "--danger")
    ),
    # The depiction's own legend and annotations, on the fixed molecule ground.
    Obligation("--mol-label", ("--mol-canvas",), TEXT_FLOOR, "depiction legend"),
    # Non-text: control outlines must be findable, decoration must be visible.
    Obligation("--border-control", ("--bg",), NONTEXT_FLOOR, "input outline"),
    Obligation("--border-control", ("--bg-elevated",), NONTEXT_FLOOR, "input outline on a card"),
    Obligation("--text-tertiary", ("--bg",), NONTEXT_FLOOR, "decoration (dots, rules)"),
)

# Element colours are chemical identity and are never adjusted to pass a
# contrast floor. If one is below the floor it is published here, with the
# measured ratio, rather than corrected — the same answer docs/VALIDATION.md
# gives about the 1HSG benchmark. The check fails if a listed element gets
# WORSE, and fails if an element NOT listed here drops below the floor.
#
# Deliberately empty: CPK_2D is RDKit's Avalon palette, whose worst case is
# oxygen at 4.00:1. Emptiness is the point of the mechanism, not the absence of
# one — an element added below 3:1 fails here until somebody writes down its
# number and why it is acceptable.
CPK_2D_BELOW_FLOOR: dict[str, float] = {}

# The other way an element palette fails a chemist: two DIFFERENT elements that
# look the same. Avalon buys its contrast with hue, so the halogens collapse to
# one green. That is a real cost and it is gated rather than merely mentioned,
# because the failure mode it invites is a fourth element quietly joining the
# pile. Identity is still carried by the atom symbol the depiction draws, which
# is why these are acceptable at all.
#
# Keys are sorted element-key pairs; values are the measured CIE76 dE.
CPK_2D_INDISTINGUISHABLE: dict[tuple[str, str], float] = {
    ("17", "9"): 0.0,  # Cl / F  — identical #007F00
    ("35", "9"): 0.0,  # Br / F  — identical
    ("17", "35"): 0.0,  # Cl / Br — identical
    ("15", "53"): 23.5,  # P / I  — both purple
}

# CPK_3D, the Jmol table, against --viewer-canvas. Two elements are below the
# floor and are published rather than fixed, because there is nowhere to move
# them to: a sweep of every grey ground puts the best achievable worst-case at
# 2.69 (pure black), so NO ground clears this table. The one alternative 3Dmol
# ships, its `rasmol` table, still fails bromine at 2.67 AND introduces five
# collisions including boron/chlorine identical — a bad trade in a medium where
# colour is the only identity channel, because a 3D scene draws no atom labels.
#
# The 3:1 floor is applied here as a CONSERVATIVE PROXY, not because WCAG 1.4.11
# is in scope. A 3D atom is a lit sphere with a specular highlight, an outline
# and depth cues, so its rendered pixels span a range around the base colour and
# a flat base-vs-ground ratio understates what a viewer can see. Holding it to
# the flat-graphics standard anyway means these two numbers are an upper bound
# on the problem rather than a description of it.
CPK_3D_BELOW_FLOOR: dict[str, float] = {
    "Br": 2.68,
    "I": 2.42,
}

# None, and it matters more here than in 2D: the 2D depiction draws the atom
# symbol beside every heteroatom, so colour there is a redundant channel. A 3D
# scene draws no labels at all. If two elements collide in CPK_3D, the
# information is gone rather than merely harder to read.
CPK_3D_INDISTINGUISHABLE: dict[tuple[str, str], float] = {}

# Below this, two element colours are close enough that a reader scanning a
# structure will not reliably tell them apart. 25 is the conventional "clearly
# different colours" threshold for CIE76; anything under it must be published
# in CPK_2D_INDISTINGUISHABLE above.
ELEMENT_DELTA_E_FLOOR = 25.0

# Hydrogen and carbon are the skeleton and are drawn in the same colour on
# purpose, so they are not a collision.
SKELETON_ELEMENTS = frozenset({"-1", "1", "6", "H", "C"})


def _colour_of(token: str, decls: dict[str, str]) -> tuple[float, float, float, float] | None:
    if token not in decls:
        return None
    return parse_colour(resolve(decls[token], decls))


def check_contrast(
    themes: dict[str, dict[str, str]], cpk: dict[str, dict[str, str]]
) -> tuple[list[str], list[str]]:
    """Returns (problems, report lines)."""
    problems: list[str] = []
    report: list[str] = []
    shared = themes.get("", {})

    for theme in sorted(t for t in themes if t):
        decls = {**shared, **themes[theme]}
        report.append(f"\n  [{theme}]")
        for ob in CONTRAST_OBLIGATIONS:
            fg = _colour_of(ob.fg, decls)
            if fg is None:
                problems.append(f"[{theme}] {ob.fg} is not defined but is under a contrast rule")
                continue
            grounds = [_colour_of(g, decls) for g in ob.ground]
            if any(g is None for g in grounds):
                missing = [g for g, c in zip(ob.ground, grounds, strict=True) if c is None]
                problems.append(
                    f"[{theme}] {', '.join(missing)} is not defined but is a contrast ground"
                )
                continue
            # Flatten right-to-left: the last ground is the opaque surface.
            ground = grounds[-1][:3]  # type: ignore[index]
            for tint in reversed(grounds[:-1]):
                ground = composite(tint, ground)  # type: ignore[arg-type]
            ratio = contrast_ratio(composite(fg, ground), ground)
            mark = "ok " if ratio >= ob.floor else "FAIL"
            over = " on ".join(ob.ground)
            report.append(f"    {mark} {ratio:5.2f} (>= {ob.floor})  {ob.fg} on {over}  — {ob.where}")
            if ratio < ob.floor:
                problems.append(
                    f"[{theme}] {ob.fg} on {over} is {ratio:.2f}:1, below the "
                    f"{ob.floor}:1 floor for {ob.where}"
                )

    # Element colours, against the ground each is defined for. The grounds are
    # identical in every theme (check 2 enforces that), so measure once.
    any_theme = next(d for t, d in themes.items() if t)
    decls = {**shared, **any_theme}
    for name, ground_token, below in (
        ("CPK_2D", "--mol-canvas", CPK_2D_BELOW_FLOOR),
        ("CPK_3D", "--viewer-canvas", CPK_3D_BELOW_FLOOR),
    ):
        ground = _colour_of(ground_token, decls)
        if ground is None:
            problems.append(
                f"{ground_token} is not defined; {name}'s colours have no ground "
                f"to be checked against"
            )
            continue
        problems += check_element_contrast(name, cpk.get(name, {}), ground_token, ground, below, report)

    problems += check_element_discriminability("CPK_2D", cpk.get("CPK_2D", {}), report)
    problems += check_element_discriminability("CPK_3D", cpk.get("CPK_3D", {}), report)
    return problems, report


def _element_sort_key(item: tuple[str, str]) -> tuple[int, int | str]:
    """CPK_2D is keyed by atomic number, CPK_3D by element symbol."""
    key = item[0]
    try:
        return (0, int(key))
    except ValueError:
        return (1, key)


def check_element_contrast(
    name: str,
    palette: dict[str, str],
    ground_token: str,
    ground: tuple[float, float, float, float],
    below_floor: dict[str, float],
    report: list[str],
) -> list[str]:
    """Every element colour against the ground its palette is defined for.
    A shortfall is published with its number, never corrected — the colours are
    chemical identity, so one getting worse means the GROUND moved."""
    problems: list[str] = []
    published = dict(below_floor)
    report.append(f"\n  [{name} on {ground_token}]")
    for element, hexv in sorted(palette.items(), key=_element_sort_key):
        colour = parse_colour(hexv)
        if colour is None:
            problems.append(f"{name}[{element}] = {hexv} is not a colour")
            continue
        ratio = contrast_ratio(colour[:3], ground[:3])
        was = published.pop(element, None)
        if was is not None:
            mark = "pub " if ratio >= was - 0.005 else "FAIL"
            report.append(
                f"    {mark} {ratio:5.2f} "
                f"(published below the {NONTEXT_FLOOR}:1 floor at {was})  {element}"
            )
            if ratio < was - 0.005:
                problems.append(
                    f"{name}[{element}] is {ratio:.2f}:1 on {ground_token}, worse than the "
                    f"{was}:1 published in cpk.ts — element colours are not adjusted, so "
                    f"this means the GROUND moved"
                )
        else:
            mark = "ok " if ratio >= NONTEXT_FLOOR else "FAIL"
            report.append(f"    {mark} {ratio:5.2f} (>= {NONTEXT_FLOOR})  {element}")
            if ratio < NONTEXT_FLOOR:
                problems.append(
                    f"{name}[{element}] is {ratio:.2f}:1 on {ground_token}, below the "
                    f"{NONTEXT_FLOOR}:1 floor and not listed in {name}_BELOW_FLOOR. Either "
                    f"the ground moved, or a new element colour needs its shortfall published"
                )
    for element in published:
        problems.append(
            f"{name}_BELOW_FLOOR lists {element}, but {name} no longer defines it; "
            f"remove the entry"
        )
    return problems


def check_element_discriminability(
    name: str, palette: dict[str, str], report: list[str]
) -> list[str]:
    """Two different elements drawn in the same colour is the other way an
    element palette fails, and it is the one a contrast floor does not catch."""
    problems: list[str] = []
    elements = sorted(z for z in palette if z not in SKELETON_ELEMENTS)
    published = dict(
        CPK_2D_INDISTINGUISHABLE if name == "CPK_2D" else CPK_3D_INDISTINGUISHABLE
    )
    report.append(f"\n  [{name} element pairs closer than dE {ELEMENT_DELTA_E_FLOOR}]")
    found = False
    for i, a in enumerate(elements):
        for b in elements[i + 1 :]:
            colour_a, colour_b = parse_colour(palette[a]), parse_colour(palette[b])
            if colour_a is None or colour_b is None:
                continue
            distance = delta_e(colour_a[:3], colour_b[:3])
            if distance >= ELEMENT_DELTA_E_FLOOR:
                continue
            found = True
            key = tuple(sorted((a, b)))
            was = published.pop(key, None)  # type: ignore[arg-type]
            if was is None:
                report.append(f"    FAIL {distance:5.1f}  {a} / {b}")
                problems.append(
                    f"{name}[{a}] and {name}[{b}] are dE {distance:.1f} apart, under the "
                    f"{ELEMENT_DELTA_E_FLOOR} floor, and are not listed in "
                    f"{name}_INDISTINGUISHABLE. Two elements a reader cannot tell apart is "
                    f"a defect even when both clear the contrast floor — publish it with "
                    f"its number, or pick a colour that separates them"
                )
            else:
                report.append(f"    pub  {distance:5.1f}  {a} / {b} (published at {was})")
                if distance < was - 0.05:
                    problems.append(
                        f"{name}[{a}] and {name}[{b}] are dE {distance:.1f} apart, closer "
                        f"than the {was} published in check_design_tokens.py"
                    )
    for key in published:
        gone = [z for z in key if z not in palette]
        if gone:
            problems.append(
                f"{name}_INDISTINGUISHABLE lists {key}, but {name} no longer defines "
                f"{', '.join(f'Z={z}' for z in gone)}; remove the entry"
            )
        else:
            problems.append(
                f"{name}_INDISTINGUISHABLE lists {key} but those two are now far enough "
                f"apart; remove the entry rather than leaving a published defect that no "
                f"longer exists"
            )
    if not found:
        report.append("    none — every element pair is distinguishable")
    return problems


# ---------------------------------------------------------------------------
# Check 4 — the ratios written in tokens.css are true.
# ---------------------------------------------------------------------------

# A declaration comment may quote contrast ratios, and every one of them is
# recomputed here. The form is fixed so it can be: `N.NN:1 on --token`. A ratio
# written without a ground is unfalsifiable, so it is an error rather than
# something skipped — which is the whole point of the file saying "a ratio
# written here that stops being true fails a build".
_DECL_LINE_RE = re.compile(r"^\s*(--[a-z0-9-]+)\s*:\s*([^;]+);\s*(?:/\*(.*?)\*/)?\s*$")
_STATED_RE = re.compile(r"(\d+(?:\.\d+)?):1(?:\s+on\s+(--[a-z0-9-]+))?")

# A ratio quoted against a translucent token is measured over this surface,
# because that is where those tints are painted.
TINT_GROUND = "--bg-elevated"


def check_stated_ratios(text: str, themes: dict[str, dict[str, str]]) -> list[str]:
    problems: list[str] = []
    shared = themes.get("", {})
    theme = ""
    for lineno, raw in enumerate(text.splitlines(), start=1):
        if raw.startswith('[data-theme="'):
            theme = raw.split('"')[1]
            continue
        if raw.startswith("}"):
            theme = ""
        m = _DECL_LINE_RE.match(raw)
        if not m or not m.group(3) or not theme:
            continue
        token, comment = m.group(1), m.group(3)
        decls = {**shared, **themes[theme]}
        fg = _colour_of(token, decls)
        for stated, ground_token in _STATED_RE.findall(comment):
            if not ground_token:
                problems.append(
                    f"{TOKENS_CSS.name}:{lineno}: '{stated}:1' on {token} names no ground. "
                    f"Write it as '{stated}:1 on --some-token' so it can be checked."
                )
                continue
            ground = _colour_of(ground_token, decls)
            if fg is None or ground is None:
                problems.append(
                    f"{TOKENS_CSS.name}:{lineno}: {token} or {ground_token} "
                    f"is not defined in '{theme}'"
                )
                continue
            base = ground[:3]
            if ground[3] < 1.0:
                surface = _colour_of(TINT_GROUND, decls)
                if surface is None:
                    problems.append(
                        f"{TOKENS_CSS.name}:{lineno}: {TINT_GROUND} is needed "
                        f"to flatten {ground_token}"
                    )
                    continue
                base = composite(ground, surface[:3])
            actual = contrast_ratio(composite(fg, base), base)
            if abs(actual - float(stated)) > 0.005:
                problems.append(
                    f"{TOKENS_CSS.name}:{lineno} [{theme}]: {token} on {ground_token} is "
                    f"{actual:.2f}:1, but the comment says {stated}:1"
                )
    return problems


# ---------------------------------------------------------------------------
# Entrypoint.
# ---------------------------------------------------------------------------


def main() -> int:
    themes = parse_tokens_css(TOKENS_CSS.read_text(encoding="utf-8"))
    cpk = parse_cpk_ts(CPK_TS.read_text(encoding="utf-8"))
    problems: list[str] = []

    # 1 — raw colour literals.
    violations = scan_colour_literals(SRC)
    print(f"raw colour literals outside the palette: {len(violations)} (ceiling {TOKEN_LINT_CEILING})")
    for v in violations:
        print(f"  {v.path.relative_to(REPO)}:{v.line}: {v.text}")
    if len(violations) > TOKEN_LINT_CEILING:
        problems.append(
            f"{len(violations)} raw colour literals, above the committed ceiling of "
            f"{TOKEN_LINT_CEILING}. Reach the colour through a token in "
            f"{TOKENS_CSS.relative_to(REPO)} instead."
        )
    elif len(violations) < TOKEN_LINT_CEILING:
        problems.append(
            f"{len(violations)} raw colour literals, below the committed ceiling of "
            f"{TOKEN_LINT_CEILING} — lower TOKEN_LINT_CEILING to {len(violations)} in this "
            f"file. The ceiling only goes down; slack left in it is where the next one hides."
        )

    # 1b — undefined token reads.
    defined = {t for decls in themes.values() for t in decls}
    undefined = scan_undefined_tokens(SRC, defined)
    for u in undefined:
        problems.append(f"{u.path.relative_to(REPO)}:{u.line}: {u.text}")
    if not undefined:
        print(f"every var(--token) read under {SRC.relative_to(REPO)} resolves to a defined token")

    # 2 — theme parity.
    named = sorted(t for t in themes if t)
    print(f"\nthemes defined: {', '.join(named) or '(none)'}")
    parity = check_parity(
        themes,
        parse_cpk_grounds(CPK_TS.read_text(encoding="utf-8")),
        parse_declared_themes(THEME_TS.read_text(encoding="utf-8")),
    )
    problems += parity
    if not parity:
        count = len(next(iter(themes[t] for t in named), {}))
        print(f"  every theme defines the same {count} tokens")

    # 3 — contrast.
    contrast_problems, report = check_contrast(themes, cpk)
    print("\ncontrast:")
    print("\n".join(report))
    problems += contrast_problems

    # 4 — the ratios the palette file claims about itself.
    stated = check_stated_ratios(TOKENS_CSS.read_text(encoding="utf-8"), themes)
    problems += stated
    if not stated:
        print("\nevery contrast ratio quoted in tokens.css recomputes to the value it states")

    if problems:
        print(f"\n{len(problems)} problem(s):", file=sys.stderr)
        for p in problems:
            print(f"  - {p}", file=sys.stderr)
        return 1
    print("\ndesign-token contract holds.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
