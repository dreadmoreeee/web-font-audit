from web_font_audit.css import (
    parse_family_list,
    parse_font_faces,
    parse_imports,
    parse_unicode_range,
    parse_weight,
    split_top,
)

BASE = "https://example.test/css/site.css"


def test_font_face_basics_and_relative_urls():
    css = """
    /* @font-face { font-family: Commented; src: url(x.woff2); } */
    @font-face {
      font-family: "Open Sans";
      src: local("Open Sans"), local(OpenSans-Regular),
           url(../fonts/open.woff2#iefix) format("woff2"), url('/fonts/open.woff') format('woff');
      font-weight: 300 800;
      font-style: italic;
      font-display: SWAP;
      unicode-range: U+0000-00FF, U+0131, U+4??;
    }
    """
    [face] = parse_font_faces(css, BASE)
    assert face.family == "Open Sans"
    assert face.local_names == ["Open Sans", "OpenSans-Regular"]
    assert face.urls == ["https://example.test/fonts/open.woff2", "https://example.test/fonts/open.woff"]
    assert [s.format for s in face.sources if s.kind == "url"] == ["woff2", "woff"]
    assert face.weight == (300, 800) and face.weight_text() == "300 800"
    assert face.style == "italic"
    assert face.display == "swap" and face.display_declared
    assert face.unicode_range == [(0, 0xFF), (0x131, 0x131), (0x400, 0x4FF)]
    assert face.covers(0x41) and face.covers(0x4AA) and not face.covers(0x3A9)


def test_defaults_when_descriptors_missing():
    [face] = parse_font_faces("@font-face{font-family:X;src:url(x.ttf)}", BASE)
    assert face.display == "auto" and not face.display_declared
    assert face.unicode_range is None and face.covers(0x1F600)
    assert face.weight == (400, 400) and face.style == "normal"
    assert face.to_dict()["font_display"] is None


def test_data_uri_with_semicolons_and_nested_rules():
    css = """
    @media (min-width: 1px) {
      @supports (display: grid) {
        @font-face { font-family: 'Inline'; src: url(data:font/woff2;base64,d09GMgAB) format('woff2');
                     font-weight: bold; }
      }
    }
    .a { color: red; }
    @font-face { font-family: Second; src: url("b.woff2"); font-weight: normal }
    """
    faces = parse_font_faces(css, BASE)
    assert [f.family for f in faces] == ["Inline", "Second"]
    assert faces[0].urls == ["data:font/woff2;base64,d09GMgAB"]
    assert faces[0].weight == (700, 700)
    assert faces[1].urls == ["https://example.test/css/b.woff2"]


def test_family_list_and_split():
    assert parse_family_list('"Open  Sans", Arial, \'Font, With Comma\', sans-serif') == [
        "open sans", "arial", "font, with comma", "sans-serif"]
    assert split_top("a(b;c);d;'e;f'", ";") == ["a(b;c)", "d", "'e;f'"]


def test_unicode_range_ignores_garbage():
    assert parse_unicode_range("U+20AC, junk, U+ZZ, u+30-39") == [(0x20AC, 0x20AC), (0x30, 0x39)]


def test_weight_keywords():
    assert parse_weight("bold") == (700, 700)
    assert parse_weight("900 100") == (100, 900)
    assert parse_weight("") == (400, 400)


def test_imports():
    css = '@import url("fonts.css"); @import \'https://cdn.test/a.css\' screen; @import url(b.css);'
    assert parse_imports(css, BASE) == [
        "https://example.test/css/fonts.css", "https://cdn.test/a.css", "https://example.test/css/b.css"]
