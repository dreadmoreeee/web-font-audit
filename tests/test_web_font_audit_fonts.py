import pytest
from fontTools.ttLib import woff2 as ft_woff2

from web_font_audit import fonts


def test_detect_format(fontmaker):
    assert fonts.detect_format(fontmaker()) == "ttf"
    assert fonts.detect_format(fontmaker(flavor="woff")) == "woff"
    assert fonts.detect_format(fontmaker(flavor="woff2")) == "woff2"
    assert fonts.detect_format(b"OTTO" + b"\0" * 10) == "otf"
    eot = bytearray(40)
    eot[34:36] = b"LP"
    assert fonts.detect_format(bytes(eot)) == "eot"
    assert fonts.detect_format(b"<html>") == "unknown"


def test_parse_ttf_and_woff(fontmaker):
    for flavor in (None, "woff"):
        font = fonts.parse_font(fontmaker("Parse Me", flavor=flavor))
        assert font.name.startswith("Parse Me")
        assert 0x41 in font.cmap and 0x3A9 in font.cmap
        assert font.glyphs == len(font.cmap) + 1
        assert fonts.detect_format(font.sfnt) == "ttf"


def test_parse_woff2_with_a_decompressor_only(fontmaker, stored_brotli):
    data = fontmaker(flavor="woff2")
    if not ft_woff2.haveBrotli:
        with pytest.raises(ValueError):
            fonts.parse_font(data)
    font = fonts.parse_font(data, stored_brotli.decompress)
    assert 0x41 in font.cmap
    # the temporary patch is undone
    assert ft_woff2.haveBrotli == (fonts.brotli_module() is not None)


def test_subset_is_real_and_smaller(fontmaker):
    font = fonts.parse_font(fontmaker())
    full = fonts.encode(font.sfnt, "woff")
    latin = fonts.subset(font.sfnt, fonts.latin_codepoints() & font.cmap, "woff")
    tiny = fonts.subset(font.sfnt, {ord(c) for c in "Hi"}, "woff")
    assert len(tiny) < len(latin) < len(full)
    kept = fonts.parse_font(latin).cmap
    assert 0x41 in kept and 0x3A9 not in kept


def test_eot_is_not_parsed():
    eot = bytearray(64)
    eot[34:36] = b"LP"
    with pytest.raises(ValueError):
        fonts.parse_font(bytes(eot))


def test_latin_codepoints():
    cps = fonts.latin_codepoints()
    assert {0x41, 0xE9, 0x20AC, 0x2019} <= cps
    assert 0x3A9 not in cps and 0x4E2D not in cps
