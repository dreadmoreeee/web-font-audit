"""End-to-end: real Chromium against local servers with generated fonts."""

import json

from web_font_audit.analyze import Analyzer


def test_full_page_audit(pages, collector):
    site, remote = pages
    data = collector.collect(site.url("/"))
    assert not data.error, data.error
    report = Analyzer(decompress=collector.decompress).analyze(data)
    fonts = {f.url.rsplit("/", 1)[-1]: f for f in report.fonts}

    # every file that was downloaded, and nothing that was not
    assert set(fonts) == {"body.ttf", "head.woff2", "below.woff", "icons.ttf",
                          "orphan.woff2", "remote.woff"}
    assert "never.woff2" not in fonts
    assert fonts["head.woff2"].format == "woff2"
    assert fonts["body.ttf"].format == "ttf"
    assert fonts["below.woff"].format == "woff"
    assert fonts["remote.woff"].party == "third-party"
    assert fonts["body.ttf"].party == "first-party"
    assert fonts["head.woff2"].transfer_bytes >= fonts["head.woff2"].decoded_bytes > 0

    # WOFF2 parsed (through the brotli module or the browser bridge)
    assert fonts["head.woff2"].glyphs and fonts["head.woff2"].cmap_size > 300
    assert fonts["head.woff2"].preloaded

    # characters attributed per family, above the fold only where visible
    assert set("Hello fonts") <= {chr(c) for c in fonts["head.woff2"].used_chars}
    assert fonts["head.woff2"].above_chars
    assert fonts["below.woff"].used_chars and not fonts["below.woff"].above_chars
    assert 0xE001 in fonts["icons.ttf"].used_chars
    assert 0x3A9 in fonts["body.ttf"].used_chars
    assert 0x4E2D in fonts["body.ttf"].missing_chars
    assert not fonts["orphan.woff2"].used

    # @font-face rules from inline, same-origin and cross-origin sheets
    by_family = {f.family: f for f in report.faces}
    assert set(by_family) == {"Body", "Head", "Never", "Below", "Icons", "Remote"}
    assert by_family["Below"].local_names == ["Below Font"]
    assert by_family["Icons"].unicode_range == [(0xE000, 0xE0FF)]
    assert not report.face_used[by_family["Never"].order]

    codes = {(f.code, f.url.rsplit("/", 1)[-1]) for f in report.findings}
    assert ("font-display", "body.ttf") in codes          # not set
    assert ("font-display", "remote.woff") in codes       # block
    assert ("font-display", "icons.ttf") in codes         # block
    assert ("font-display", "head.woff2") not in codes    # swap
    assert ("legacy-format", "body.ttf") in codes
    assert ("legacy-format", "below.woff") in codes
    assert ("unused-preload", "orphan.woff2") in codes
    assert ("preload-crossorigin", "orphan.woff2") in codes
    assert ("preload-crossorigin", "head.woff2") not in codes
    assert ("loaded-unused", "orphan.woff2") in codes
    assert ("third-party", "remote.woff") in codes
    assert ("missing-glyphs", "body.ttf") in codes
    assert ("missing-preload", "body.ttf") in codes
    assert ("missing-preload", "below.woff") not in codes
    assert any(f.code == "declared-unused" and "Never" in f.message for f in report.findings)

    # real subsets, smaller than the originals
    head = fonts["head.woff2"].subset
    assert head["page_subset_bytes"] < head["latin_subset_bytes"] < head["reference_bytes"]
    assert any(f.code == "subset" for f in report.findings)

    doc = report.to_dict()
    assert doc["totals"]["font_files"] == 6
    assert doc["totals"]["third_party"] == 1
    json.dumps(doc)


def test_brotli_bridge_decodes_through_the_browser(collector, stored_brotli):
    payload = bytes(range(256)) * 700  # > 64 KiB: several meta-blocks
    assert collector.decompress(stored_brotli.compress(payload)) == payload
