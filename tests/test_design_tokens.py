"""The design-token gate, tested on inputs that should fail it.

A lint whose failure path is never exercised is a lint that quietly stops
failing. Every check in `scripts/check_design_tokens.py` is given something
broken here as well as something correct, and the last test runs the whole
thing against the real desktop app.
"""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

import scripts.check_design_tokens as cdt
from scripts.check_design_tokens import (
    CPK_TS,
    THEME_TS,
    TOKENS_CSS,
    check_contrast,
    check_element_discriminability,
    check_parity,
    check_stated_ratios,
    composite,
    contrast_ratio,
    main,
    parse_colour,
    parse_cpk_grounds,
    parse_cpk_ts,
    parse_declared_themes,
    parse_tokens_css,
    resolve,
    scan_colour_literals,
    scan_undefined_tokens,
)

# ---------------------------------------------------------------------------
# Colour maths. The expected values are WCAG's own worked examples.
# ---------------------------------------------------------------------------


def test_black_on_white_is_the_maximum_ratio() -> None:
    assert contrast_ratio((0, 0, 0), (255, 255, 255)) == pytest.approx(21.0)


def test_a_colour_against_itself_is_1_to_1() -> None:
    assert contrast_ratio((29, 155, 240), (29, 155, 240)) == pytest.approx(1.0)


def test_white_on_twitter_blue_is_the_3_00_failure_the_palette_exists_to_fix() -> None:
    # The single number that justifies --accent-strong. If this moves, the
    # argument in tokens.css's header stops being true.
    assert contrast_ratio((255, 255, 255), (29, 155, 240)) == pytest.approx(3.00, abs=0.005)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("#fff", (255.0, 255.0, 255.0, 1.0)),
        ("#15202b", (21.0, 32.0, 43.0, 1.0)),
        ("#ffffff80", (255.0, 255.0, 255.0, pytest.approx(0.502, abs=0.001))),
        ("rgb(1, 2, 3)", (1.0, 2.0, 3.0, 1.0)),
        ("rgba(29, 155, 240, 0.12)", (29.0, 155.0, 240.0, 0.12)),
        ("white", (255.0, 255.0, 255.0, 1.0)),
    ],
)
def test_parse_colour_accepts_every_form_the_stylesheet_uses(value: str, expected: tuple) -> None:
    assert parse_colour(value) == expected


@pytest.mark.parametrize("value", ["12px", "var(--bg)", "Helvetica Neue", "9999px", ""])
def test_parse_colour_rejects_what_is_not_a_colour(value: str) -> None:
    assert parse_colour(value) is None


def test_compositing_a_fully_opaque_layer_leaves_the_ground_unused() -> None:
    assert composite((10.0, 20.0, 30.0, 1.0), (200.0, 200.0, 200.0)) == (10.0, 20.0, 30.0)


def test_compositing_a_fully_transparent_layer_leaves_the_ground_alone() -> None:
    assert composite((10.0, 20.0, 30.0, 0.0), (200.0, 200.0, 200.0)) == (200.0, 200.0, 200.0)


def test_resolve_follows_a_var_chain_to_a_literal() -> None:
    decls = {"--a": "var(--b)", "--b": "#123456"}
    assert resolve("var(--a)", decls) == "#123456"


def test_resolve_uses_the_fallback_when_the_token_is_undefined() -> None:
    assert resolve("var(--nope, #abcdef)", {}) == "#abcdef"


def test_resolve_does_not_hang_on_a_cycle() -> None:
    assert resolve("var(--a)", {"--a": "var(--b)", "--b": "var(--a)"}) is not None


# ---------------------------------------------------------------------------
# Parsing.
# ---------------------------------------------------------------------------

STYLESHEET = textwrap.dedent(
    """
    :root {
      --radius: 12px; /* not a colour */
    }
    [data-theme="dim"] {
      --bg: #15202b; /* 15.61:1 on --text */
      --text: #f7f9f9;
      --mol-canvas: #ffffff;
    }
    [data-theme="light"] {
      --bg: #ffffff;
      --text: #0f1419;
      --mol-canvas: #ffffff;
    }
    """
)


def test_parse_tokens_css_separates_the_shared_block_from_the_themes() -> None:
    blocks = parse_tokens_css(STYLESHEET)
    assert set(blocks) == {"", "dim", "light"}
    assert blocks[""] == {"--radius": "12px"}
    assert blocks["dim"]["--bg"] == "#15202b"


def test_parse_tokens_css_ignores_declarations_inside_comments() -> None:
    blocks = parse_tokens_css('[data-theme="dim"] { --a: #111111; /* --b: #222222; */ }')
    assert blocks["dim"] == {"--a": "#111111"}


def test_parse_declared_themes_reads_the_switcher_list() -> None:
    assert parse_declared_themes('export const THEMES = ["dim", "light"] as const') == [
        "dim",
        "light",
    ]


# ---------------------------------------------------------------------------
# Check 1 — raw colour literals.
# ---------------------------------------------------------------------------


def _write(tmp_path: Path, name: str, body: str) -> Path:
    path = tmp_path / name
    path.write_text(textwrap.dedent(body), encoding="utf-8")
    return path


@pytest.mark.parametrize(
    "line",
    [
        "  color: #ff0000;",
        "  color: #f00;",
        "  background: rgba(1, 2, 3, 0.5);",
        "  background: hsl(200, 50%, 50%);",
        "  const SURFACE = 0x1e2732;",
    ],
)
def test_every_form_a_colour_can_take_is_caught(tmp_path: Path, line: str) -> None:
    _write(tmp_path, "leak.css", f".x {{\n{line}\n}}\n")
    assert len(scan_colour_literals(tmp_path)) == 1


def test_a_colour_named_only_in_a_comment_is_not_a_violation(tmp_path: Path) -> None:
    # The 0x form shipped once in lib/mol3d.ts and a `#`-only grep missed it;
    # the comment above it named the token, and a comment is not a commitment.
    _write(
        tmp_path,
        "ok.ts",
        """
        // The Dim elevated surface (#1e2732) as an int.
        /* also #abcdef here */
        export const X = 1;
        """,
    )
    assert scan_colour_literals(tmp_path) == []


def test_the_reported_line_number_survives_a_multi_line_comment(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "leak.css",
        """
        /* one
           two
           three */
        .x {
          color: #ff0000;
        }
        """,
    )
    (violation,) = scan_colour_literals(tmp_path)
    assert violation.line == 6


def test_an_undefined_token_read_is_caught(tmp_path: Path) -> None:
    # `--text-primary` shipped this way: read twice, defined nowhere, silently
    # resolving to a fallback that put two different whites on screen.
    _write(tmp_path, "x.css", ".a { color: var(--text-primary, #e7e9ea); }\n")
    (violation,) = scan_undefined_tokens(tmp_path, {"--text"})
    assert "--text-primary" in violation.text


def test_ketchers_own_namespace_is_not_our_problem(tmp_path: Path) -> None:
    _write(tmp_path, "x.css", ".a { color: var(--color-text-primary); }\n")
    assert scan_undefined_tokens(tmp_path, set()) == []


# ---------------------------------------------------------------------------
# Check 2 — parity.
# ---------------------------------------------------------------------------

GROUNDS = {"MOL_CANVAS": "#ffffff", "MOL_LABEL": "#536471", "VIEWER_CANVAS": "#0d1117"}


def test_a_token_defined_in_one_theme_and_not_another_fails() -> None:
    themes = {"dim": {"--a": "#111111", "--b": "#222222"}, "light": {"--a": "#eeeeee"}}
    problems = check_parity(themes, GROUNDS, ["dim", "light"])
    assert any("--b" in p and "light" in p for p in problems)


def test_a_colour_in_the_shared_root_block_fails() -> None:
    # It would escape the parity rule entirely, which is the whole point of it.
    themes = {"": {"--sneaky": "#123456"}, "dim": {}, "light": {}}
    assert any("--sneaky" in p for p in check_parity(themes, GROUNDS, ["dim", "light"]))


def test_a_non_colour_in_the_shared_root_block_is_fine() -> None:
    themes = {"": {"--radius": "12px"}, "dim": {}, "light": {}}
    assert check_parity(themes, GROUNDS, ["dim", "light"]) == []


def test_a_theme_that_moves_the_molecule_ground_fails() -> None:
    # The rule the whole rendering-molecules skill rests on: a theme change
    # must never alter a colour that encodes chemical meaning.
    themes = {"dim": {"--mol-canvas": "#ffffff"}, "light": {"--mol-canvas": "#15202b"}}
    problems = check_parity(themes, GROUNDS, ["dim", "light"])
    assert any("--mol-canvas" in p for p in problems)


def test_a_ground_that_disagrees_with_cpk_ts_fails() -> None:
    themes = {"dim": {"--viewer-canvas": "#000000"}, "light": {"--viewer-canvas": "#000000"}}
    problems = check_parity(themes, GROUNDS, ["dim", "light"])
    assert any("VIEWER_CANVAS" in p for p in problems)


def test_a_theme_offered_in_the_switcher_with_no_stylesheet_block_fails() -> None:
    themes = {"dim": {}, "light": {}}
    problems = check_parity(themes, GROUNDS, ["dim", "light", "high-contrast"])
    assert any("high-contrast" in p for p in problems)


def test_a_single_theme_is_not_a_theme_system() -> None:
    assert check_parity({"dim": {"--a": "#111111"}}, GROUNDS, ["dim"]) != []


# ---------------------------------------------------------------------------
# Check 3 — contrast.
# ---------------------------------------------------------------------------


def _theme(**tokens: str) -> dict[str, dict[str, str]]:
    base = {
        "--bg": "#ffffff",
        "--bg-elevated": "#ffffff",
        "--bg-elevated-2": "#ffffff",
        "--bg-input": "#ffffff",
        "--text": "#000000",
        "--text-secondary": "#000000",
        "--text-tertiary": "#000000",
        "--text-on-accent": "#000000",
        "--accent": "#000000",
        "--accent-strong": "#ffffff",
        "--accent-strong-hover": "#ffffff",
        "--accent-strong-pressed": "#ffffff",
        "--border-control": "#000000",
        "--mol-canvas": "#ffffff",
        "--mol-label": "#000000",
        "--success": "#000000",
        "--success-subtle": "rgba(0, 0, 0, 0.1)",
        "--warning": "#000000",
        "--warning-subtle": "rgba(0, 0, 0, 0.1)",
        "--danger": "#000000",
        "--danger-subtle": "rgba(0, 0, 0, 0.1)",
    }
    base.update(tokens)
    return {"": {}, "dim": base}


def test_a_palette_that_clears_every_floor_reports_nothing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(cdt, "CPK_2D_INDISTINGUISHABLE", {})
    problems, _ = check_contrast(_theme(), {"CPK_2D": {"6": "#000000"}})
    assert problems == []


def test_low_contrast_body_text_fails() -> None:
    problems, _ = check_contrast(_theme(**{"--text": "#eeeeee"}), {"CPK_2D": {}})
    assert any("--text on --bg" in p for p in problems)


def test_a_white_label_on_x_s_own_blue_fails_the_button_rule() -> None:
    themes = _theme(**{"--text-on-accent": "#ffffff", "--accent-strong": "#1d9bf0"})
    problems, _ = check_contrast(themes, {"CPK_2D": {}})
    assert any("--text-on-accent on --accent-strong" in p for p in problems)


def test_a_tint_is_composited_over_its_surface_before_measuring() -> None:
    # Green-on-green: fine against the bare card, too close on the tint. The
    # bug this exists to catch is a chip whose text and background drift apart.
    themes = _theme(**{"--success": "#006e4c", "--success-subtle": "rgba(0, 110, 76, 0.9)"})
    problems, _ = check_contrast(themes, {"CPK_2D": {}})
    assert any("--success-subtle" in p for p in problems)


def test_a_new_element_colour_below_the_floor_must_publish_its_shortfall() -> None:
    # Zinc, Jmol #7d80b0, 3.5:1 on white — but a hypothetical pale one is not.
    problems, _ = check_contrast(_theme(), {"CPK_2D": {"30": "#f0f0f0"}})
    assert any("CPK_2D[30]" in p and "not listed" in p for p in problems)


def test_a_published_shortfall_fails_only_if_it_gets_worse(monkeypatch: pytest.MonkeyPatch) -> None:
    # CPK_2D_BELOW_FLOOR is empty today, because Avalon's worst case is 4.00:1.
    # The mechanism still has to work for the day it is not.
    monkeypatch.setattr(cdt, "CPK_2D_BELOW_FLOOR", {"16": 1.72})
    monkeypatch.setattr(cdt, "CPK_2D_INDISTINGUISHABLE", {})
    ok, _ = check_contrast(_theme(), {"CPK_2D": {"16": "#cccc00"}})
    assert ok == []
    # The colours never move, so a published shortfall getting worse means the
    # GROUND moved underneath it.
    worse, _ = check_contrast(_theme(**{"--mol-canvas": "#ffff00"}), {"CPK_2D": {"16": "#cccc00"}})
    assert any("CPK_2D[16]" in p for p in worse)


def test_nothing_in_the_shipped_palette_is_below_the_floor() -> None:
    # The reason CPK_2D is Avalon rather than RDKit's familiar default.
    assert cdt.CPK_2D_BELOW_FLOOR == {}


# ---------------------------------------------------------------------------
# Check 3b — two different elements that look the same.
# ---------------------------------------------------------------------------


def test_identical_colours_for_two_elements_are_caught(monkeypatch: pytest.MonkeyPatch) -> None:
    # Not a contrast problem: both clear the floor comfortably. It is still a
    # depiction in which chlorine and bromine are the same mark.
    monkeypatch.setattr(cdt, "CPK_2D_INDISTINGUISHABLE", {})
    problems, _ = check_contrast(_theme(), {"CPK_2D": {"7": "#0000FF", "8": "#0000FF"}})
    assert any("dE 0.0 apart" in p for p in problems)


def test_a_published_collision_passes_but_is_still_reported(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(cdt, "CPK_2D_INDISTINGUISHABLE", {("17", "9"): 0.0})
    report: list[str] = []
    problems = check_element_discriminability({"9": "#007F00", "17": "#007F00"}, report)
    assert problems == []
    assert any("pub" in line and "0.0" in line for line in report)


def test_a_published_collision_getting_closer_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cdt, "CPK_2D_INDISTINGUISHABLE", {("15", "53"): 23.5})
    report: list[str] = []
    problems = check_element_discriminability({"15": "#7F007F", "53": "#7F017F"}, report)
    assert any("closer than the 23.5" in p for p in problems)


def test_a_collision_that_no_longer_exists_must_be_removed(monkeypatch: pytest.MonkeyPatch) -> None:
    # A stale entry is a published defect that is not real any more, which is
    # its own kind of false claim.
    monkeypatch.setattr(cdt, "CPK_2D_INDISTINGUISHABLE", {("9", "17"): 0.0})
    problems = check_element_discriminability({"9": "#007F00", "17": "#FF0000"}, [])
    assert any("remove the entry" in p for p in problems)


def test_the_skeleton_elements_are_not_a_collision(monkeypatch: pytest.MonkeyPatch) -> None:
    # H, C and the fallback are all black on purpose.
    monkeypatch.setattr(cdt, "CPK_2D_INDISTINGUISHABLE", {})
    assert check_element_discriminability({"-1": "#000000", "1": "#000000", "6": "#000000"}, []) == []


def test_delta_e_matches_the_values_published_in_the_checker() -> None:
    black, white = (0.0, 0.0, 0.0), (255.0, 255.0, 255.0)
    assert cdt.delta_e(black, black) == pytest.approx(0.0)
    # L* runs 0-100, so black to white is 100 with no chroma term.
    assert cdt.delta_e(black, white) == pytest.approx(100.0, abs=0.01)


# ---------------------------------------------------------------------------
# Check 4 — the ratios the stylesheet claims about itself.
# ---------------------------------------------------------------------------


def test_a_correct_stated_ratio_passes() -> None:
    css = '[data-theme="dim"] {\n  --text: #ffffff; /* 21.00:1 on --bg */\n  --bg: #000000;\n}\n'
    assert check_stated_ratios(css, parse_tokens_css(css)) == []


def test_a_stated_ratio_that_is_wrong_fails() -> None:
    css = '[data-theme="dim"] {\n  --text: #ffffff; /* 9.99:1 on --bg */\n  --bg: #000000;\n}\n'
    problems = check_stated_ratios(css, parse_tokens_css(css))
    assert any("21.00:1, but the comment says 9.99" in p for p in problems)


def test_a_ratio_with_no_ground_named_is_unfalsifiable_and_therefore_an_error() -> None:
    css = '[data-theme="dim"] {\n  --text: #ffffff; /* 4.50:1 */\n}\n'
    problems = check_stated_ratios(css, parse_tokens_css(css))
    assert any("names no ground" in p for p in problems)


# ---------------------------------------------------------------------------
# The real thing.
# ---------------------------------------------------------------------------


def test_the_desktop_app_satisfies_its_own_token_contract(capsys: pytest.CaptureFixture) -> None:
    assert main() == 0, capsys.readouterr().err


def test_the_files_the_gate_reads_are_where_it_thinks_they_are() -> None:
    for path in (TOKENS_CSS, CPK_TS, THEME_TS):
        assert path.is_file(), path


def test_cpk_ts_still_exports_both_palettes_and_all_three_grounds() -> None:
    palettes = parse_cpk_ts(CPK_TS.read_text(encoding="utf-8"))
    assert set(palettes) == {"CPK_2D", "CPK_3D"}
    # Oxygen red, nitrogen blue, sulfur yellow, in both renderings.
    assert palettes["CPK_2D"]["8"].lower().startswith("#ff")
    assert palettes["CPK_3D"]["O"].lower().startswith("#ff")
    assert set(parse_cpk_grounds(CPK_TS.read_text(encoding="utf-8"))) == set(GROUNDS)


def test_a_collision_entry_for_an_element_that_is_gone_is_caught(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(cdt, "CPK_2D_INDISTINGUISHABLE", {("9", "17"): 0.0})
    problems = check_element_discriminability({"9": "#007F00"}, [])
    assert any("no longer defines Z=17" in p for p in problems)
