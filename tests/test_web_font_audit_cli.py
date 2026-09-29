"""The command line: budgets, exit codes and output files (real Chromium, local servers)."""

import json

from web_font_audit.cli import main


def test_cli_budgets_and_outputs(pages, tmp_path, capsys):
    site, _ = pages
    json_path = tmp_path / "r.json"
    md_path = tmp_path / "r.md"
    code = main([site.url("/"), "--max-fonts", "2", "--fail-on", "font-display",
                 "--json-out", str(json_path), "--md-out", str(md_path), "--no-subset"])
    assert code == 1
    doc = json.loads(json_path.read_text(encoding="utf-8"))
    failures = doc["pages"][0]["budget_failures"]
    assert any(f.startswith("font files 6 > budget 2") for f in failures)
    assert any(f.startswith("font-display") for f in failures)
    assert doc["budget_failed"] is True
    md = md_path.read_text(encoding="utf-8")
    assert "## " + site.url("/") in md and "Budget exceeded" in md
    assert "# Web font audit" in capsys.readouterr().out


def test_cli_within_budget(site, fontmaker, capsys):
    site.add("/f.woff2", fontmaker("Only", flavor="woff2"))
    site.add("/", """<!doctype html><html><head>
<link rel="preload" href="/f.woff2" as="font" type="font/woff2" crossorigin>
<style>@font-face { font-family: Only; src: url(/f.woff2) format("woff2"); font-display: swap; }
body { font-family: Only, sans-serif; }</style></head><body><h1>Just one font</h1></body></html>""")
    code = main([site.url("/"), "--max-fonts", "1", "--max-font-bytes", "500KB",
                 "--fail-on", "warning", "--format", "json"])
    out = capsys.readouterr().out
    doc = json.loads(out)
    page = doc["pages"][0]
    assert code == 0, page["budget_failures"]
    assert page["totals"]["font_files"] == 1
    assert page["fonts"][0]["preloaded"] is True
    assert page["findings"] == [] or all(f["severity"] == "info" for f in page["findings"])


def test_cli_unreachable_page(capsys):
    import socket

    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    code = main([f"http://127.0.0.1:{port}/", "--timeout", "5"])
    assert code == 2
    assert "Could not load the page" in capsys.readouterr().out
