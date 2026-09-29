"""Analysis without a browser: hand-made PageData in, findings out."""

import argparse

import pytest

from web_font_audit.analyze import Analyzer, check_budgets, match_faces, party_of, site_of
from web_font_audit.cli import parse_fail_on, parse_size
from web_font_audit.collect import FontResponse, PageData
from web_font_audit.css import parse_font_faces

PAGE = "https://www.example.test/en/"


def faces_from(css):
    faces = parse_font_faces(css, PAGE)
    for i, f in enumerate(faces):
        f.order = i
    return faces


def test_match_faces_weight_and_style():
    faces = faces_from("""
      @font-face { font-family: A; src: url(a300.woff2); font-weight: 300; }
      @font-face { font-family: A; src: url(a400.woff2); font-weight: 400; }
      @font-face { font-family: A; src: url(a700.woff2); font-weight: 700; }
      @font-face { font-family: A; src: url(a400i.woff2); font-weight: 400; font-style: italic; }
    """)
    pick = lambda w, s="normal": [f.urls[0].rsplit("/", 1)[-1] for f in match_faces(faces, w, s)]
    assert pick(400) == ["a400.woff2"]
    assert pick(500) == ["a400.woff2"]      # 500: nothing up to 500, then lighter
    assert pick(600) == ["a700.woff2"]      # >500: heavier first
    assert pick(200) == ["a300.woff2"]      # <400: lighter first, then heavier
    assert pick(800) == ["a700.woff2"]
    assert pick(700, "italic") == ["a400i.woff2"]


def test_match_faces_variable_range_and_segments():
    faces = faces_from("""
      @font-face { font-family: V; src: url(latin.woff2); font-weight: 100 900; unicode-range: U+0-FF; }
      @font-face { font-family: V; src: url(greek.woff2); font-weight: 100 900; unicode-range: U+370-3FF; }
    """)
    got = match_faces(faces, 650, "normal")
    assert [f.urls[0].rsplit("/", 1)[-1] for f in got] == ["greek.woff2", "latin.woff2"]


def test_party():
    assert site_of("fonts.example.co.uk") == "example.co.uk"
    assert party_of("https://cdn.example.test/f.woff2", PAGE) == "first-party"
    assert party_of("https://fonts.gstatic.com/f.woff2", PAGE) == "third-party"
    assert party_of("data:font/woff2;base64,AA", PAGE) == "inline"


def _page(fontmaker, css, usage, preloads=(), body_format=None):
    body = fontmaker("Brand", flavor=body_format)
    return PageData(
        url=PAGE, final_url=PAGE, status=200, viewport=(1366, 768),
        fonts=[FontResponse("https://www.example.test/f/brand.ttf", 200, "font/ttf",
                            len(body) + 200, len(body), body)],
        faces=faces_from(css), usage=usage, preloads=list(preloads))


def test_attribution_fallback_and_findings(fontmaker):
    css = """
      @font-face { font-family: Brand; src: url(/f/brand.ttf) format('truetype'); }
      @font-face { font-family: Unused; src: url(/f/unused.woff2) format('woff2'); font-display: swap; }
    """
    usage = [
        {"family": "Brand, Arial, sans-serif", "weight": "400", "style": "normal",
         "chars": "Hello " + chr(0x4E2D), "above": "Hello", "elements": 2},
        {"family": "Arial, Brand", "weight": "700", "style": "normal",
         "chars": "xyz", "above": "", "elements": 1},
    ]
    preloads = [{"href": "https://www.example.test/f/old.woff2", "crossorigin": True, "type": ""}]
    report = Analyzer().analyze(_page(fontmaker, css, usage, preloads))
    [font] = report.fonts
    used = {chr(c) for c in font.used_chars}
    assert used == set("Hello ")                  # "xyz" goes to Arial, first in its stack
    assert font.missing_chars == {0x4E2D}        # not in the font: falls back
    assert {chr(c) for c in font.above_chars} == set("Helo")
    assert font.subset["latin_subset_bytes"] < font.subset["reference_bytes"]
    assert font.subset["page_subset_codepoints"] == 5
    codes = [f.code for f in report.findings]
    assert codes.count("font-display") == 1
    assert "legacy-format" in codes and "unused-preload" in codes
    assert "missing-preload" in codes and "declared-unused" in codes
    assert "missing-glyphs" in codes and "subset" in codes
    assert "third-party" not in codes

    failures = check_budgets(report, max_font_bytes=1000, max_fonts=1, max_families=1,
                             fail_on=["font-display", "error"])
    assert failures[0].startswith("font bytes")
    assert any(f.startswith("font-display") for f in failures)
    assert not any(f.startswith("font files") for f in failures)
    assert check_budgets(report, max_fonts=5) == []


def test_font_display_swap_is_clean(fontmaker):
    css = "@font-face { font-family: Brand; src: url(/f/brand.ttf); font-display: optional; }"
    usage = [{"family": "Brand", "weight": "400", "style": "normal", "chars": "ok", "above": "ok",
              "elements": 1}]
    preloads = [{"href": "https://www.example.test/f/brand.ttf", "crossorigin": False, "type": ""}]
    report = Analyzer(subset=False).analyze(_page(fontmaker, css, usage, preloads))
    codes = {f.code for f in report.findings}
    assert "font-display" not in codes and "missing-preload" not in codes
    assert "preload-crossorigin" in codes and "unused-preload" not in codes
    assert report.fonts[0].subset is None


def test_google_fonts_fix_text(fontmaker):
    page = _page(fontmaker, "", [{"family": "Brand", "weight": "400", "style": "normal",
                                  "chars": "a", "above": "a", "elements": 1}])
    page.faces = parse_font_faces("@font-face { font-family: Brand; src: url(https://www.example.test/f/brand.ttf); }",
                                  "https://fonts.googleapis.com/css2?family=Brand")
    report = Analyzer(subset=False).analyze(page)
    fix = next(f.fix for f in report.findings if f.code == "font-display")
    assert "display=swap" in fix
    assert any(f.code == "google-fonts" for f in report.findings)


def test_inline_data_font_is_counted(fontmaker):
    import base64
    data = base64.b64encode(fontmaker("Inline", flavor="woff")).decode()
    page = PageData(url=PAGE, final_url=PAGE, status=200,
                    faces=faces_from("@font-face { font-family: I; src: url(data:font/woff;base64,%s); "
                                     "font-display: swap }" % data),
                    usage=[{"family": "I", "weight": "400", "style": "normal", "chars": "abc",
                            "above": "abc", "elements": 1}])
    report = Analyzer().analyze(page)
    [font] = report.fonts
    assert font.party == "inline" and font.format == "woff" and len(font.used_chars) == 3
    assert report.total_transfer == 0 and report.to_dict()["totals"]["inline_fonts"] == 1


def test_failed_page_has_no_budget_failures():
    report = Analyzer().analyze(PageData(url=PAGE, error="net::ERR_NAME_NOT_RESOLVED"))
    assert report.error and check_budgets(report, max_fonts=0) == []


def test_cli_parsers():
    assert parse_size("150000") == 150000
    assert parse_size("150KB") == 150000
    assert parse_size("150k") == 150000
    assert parse_size("1KiB") == 1024
    assert parse_size("1.5MB") == 1500000
    with pytest.raises(argparse.ArgumentTypeError):
        parse_size("lots")
    assert parse_fail_on("font-display, warning") == ["font-display", "warning"]
    with pytest.raises(argparse.ArgumentTypeError):
        parse_fail_on("nope")
