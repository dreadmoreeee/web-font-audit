# web-font-audit

What the web fonts on a page **actually cost**: which files load, how they are declared, whether text is invisible while they download, and how many bytes a real subset would save.

```
pip install .                      # or: pip install ".[woff2]" to also write WOFF2 subsets
python -m playwright install chromium
web-font-audit https://example.com/ https://example.com/pricing --json-out fonts.json
```

Python 3.10+. Dependencies: Playwright (Apache-2.0) and fontTools (MIT); `brotli` (MIT) is optional. `python -m web_font_audit` works too.

Each page is loaded in headless Chromium. The tool records every font response and reads every `@font-face` rule, including rules in cross-origin stylesheets, which it reads from the captured CSS response because the CSSOM hides them. It collects the text that is actually rendered (including `::before`/`::after` content, `text-transform` and form values) and assigns each character to the face the browser would pick (weight/style matching, `unicode-range`, and fallback when a glyph is missing). Each font is then parsed and subset **for real** with fontTools, in memory.

## What it checks

| Code | Severity | What |
|---|---|---|
| `font-display` | warning | Used face with `font-display` missing, `auto` or `block`: invisible text (FOIT) for up to 3 s. The fix for Google Fonts is `&display=swap`. |
| `legacy-format` | warning | Font served as WOFF, TTF, OTF or EOT instead of WOFF2 (detected from the file bytes, not the URL). |
| `loaded-unused` | warning | File downloaded (often by a preload) but no visible text renders with it. |
| `unused-preload` | warning | `<link rel="preload" as="font">` for a URL no used `@font-face` points at. |
| `preload-crossorigin` | warning | Font preload without `crossorigin`, so the browser can't reuse it and may download the file twice. |
| `load-error` | error | Font request returned 4xx/5xx. |
| `missing-preload` | info | Font renders above-the-fold text but is not preloaded (the top two only). |
| `subset` | info | A Latin subset (plus this page's characters) would save at least 2 KB and 10%. |
| `missing-glyphs` | info | Rendered characters the font does not contain; they fall back to another font. |
| `declared-unused` | info | `@font-face` families nobody uses on this page. |
| `third-party` | info | Font served from another site (extra connection, visitor IPs shared). |
| `google-fonts` | info | Google Fonts CSS API in use (formats depend on the User-Agent). |

For each page the report also lists: transfer and decoded bytes per file, first- vs third-party, format, the families and weight/style variants in use, characters used (and above the fold), every `@font-face` rule with its `font-display`, `unicode-range` and `local()` sources, and all font preloads.

**How subsetting is measured.** Two subsets per used font: Latin (the same code points as the Google Fonts `latin` range, plus whatever this page renders) and page-only. Only code points are dropped. OpenType features, names, hinting and tables are all kept, so the difference is what subsetting alone saves. With the `brotli` package installed, subsets are written and measured as WOFF2. Without it, they are measured as WOFF and scaled to the served file's size (marked `~`). WOFF2 files are still *read* without brotli: the compressed stream is served from a loopback-only server with `Content-Encoding: br` and decoded by Playwright. The page-only number is a ceiling, not advice: other pages need other characters.

## Measured result

My three production sites, 4 pages, run from Miramichi, NB (September 2026). Only the first page section is shown; the other three are trimmed here and are complete in [examples/demarkstudio-report.md](examples/demarkstudio-report.md) and [.json](examples/demarkstudio-report.json).

```
$ python -m web_font_audit https://demarkstudio.ca/en/ https://demarkstudio.ca/fr/conception-web/miramichi https://demo.demarkstudio.ca/riverside-pub/site https://marvin.demarkstudio.ca/
# Web font audit

| Page | Font files | Transferred | Families | Errors | Warnings | Info |
|---|---:|---:|---:|---:|---:|---:|
| https://demarkstudio.ca/en/ | 4 | 140.3 KB | 3 | 0 | 0 | 2 |
| https://demarkstudio.ca/fr/conception-web/miramichi | 3 | 100.3 KB | 3 | 0 | 0 | 1 |
| https://demo.demarkstudio.ca/riverside-pub/site | 2 | 118.7 KB | 2 | 0 | 0 | 2 |
| https://marvin.demarkstudio.ca/ | 0 | 0.0 KB | 0 | 0 | 0 | 0 |

## https://demarkstudio.ca/en/

HTTP 200, viewport 1366x768. 4 font file(s), 140.3 KB transferred (138.4 KB decoded); 3 family(ies), 4 weight/style variant(s) used; 4 first-party, 0 third-party.

| Font file | Family | Variant | Format | Transfer | Party | font-display | Preload | Chars used (above fold) |
|---|---|---|---|---:|---|---|---|---:|
| cormorant-garamond-italic-latin.woff2 | Cormorant Garamond | 400 700 italic | woff2 | 39.9 KB | first-party | swap | yes | 6 (6) |
| cormorant-garamond-latin.woff2 | Cormorant Garamond | 400 700 normal | woff2 | 38.2 KB | first-party | swap | yes | 45 (17) |
| jetbrains-mono-latin.woff2 | JetBrains Mono | 400 700 normal | woff2 | 31.8 KB | first-party | swap | yes | 35 (21) |
| instrument-sans-normal-latin.woff2 | Instrument Sans | 400 700 normal | woff2 | 30.4 KB | first-party | swap | yes | 63 (35) |

Subsetting: fontTools subsets built in memory and measured as WOFF, because the brotli package is not installed and WOFF2 cannot be written. For files served in another format, sizes are scaled by subset/original WOFF size (marked ~).

| Font file | Served | Code points in font | Latin subset | Page-only subset |
|---|---:|---:|---:|---:|
| cormorant-garamond-italic-latin.woff2 | 39.3 KB | 231 | ~36.7 KB (226 cp) | ~2.4 KB (6 cp) |
| cormorant-garamond-latin.woff2 | 37.6 KB | 229 | ~34.9 KB (224 cp) | ~12.4 KB (45 cp) |
| jetbrains-mono-latin.woff2 | 31.4 KB | 229 | ~30.9 KB (223 cp) | ~5.1 KB (35 cp) |
| instrument-sans-normal-latin.woff2 | 30.1 KB | 208 | ~30.1 KB (204 cp) | ~11.5 KB (63 cp) |

Findings:

- **INFO** `declared-unused` @font-face declared but not used on this page: Inter.
  Fix: Remove unused @font-face rules or move them to the pages that use them.
- **INFO** `missing-glyphs` Instrument Sans: 2 rendered character(s) are not in the font and fall back to another font: '✓⤢'
  Fix: Use a font build that covers these characters, or accept the fallback.

@font-face rules: 7 (4 used on this page)

| Family | Weight | Style | font-display | unicode-range | local() | Used |
|---|---|---|---|---|---|---|
| Inter | 100 900 | normal | swap | U+0-FF, U+131, U+152-153, U+2BB-2BC, ... | - | no |
| Inter | 100 900 | normal | swap | U+100-2BA, U+2BD-2C5, U+2C7-2CC, U+2C... | - | no |
| Cormorant Garamond | 400 700 | normal | swap | - | - | yes |
| Cormorant Garamond | 400 700 | italic | swap | - | - | yes |
| Instrument Sans | 400 700 | normal | swap | - | - | yes |
| Instrument Sans | 400 700 | italic | swap | - | - | no |
| JetBrains Mono | 400 700 | normal | swap | - | - | yes |

Font preloads: cormorant-garamond-latin.woff2, instrument-sans-normal-latin.woff2, jetbrains-mono-latin.woff2, cormorant-garamond-italic-latin.woff2
[... 3 page sections trimmed ...]
```

What that says, honestly:

- **demarkstudio.ca is already in good shape.** It loads 4 files and 140.3 KB, all self-hosted WOFF2 with `font-display: swap` and preloaded with `crossorigin`. The files are already Latin subsets: a Latin subset would save at most about 2.7 KB per file, below the reporting threshold. Only a page-only subset would be much smaller (e.g. 39.3 KB to 2.4 KB for the italic, which renders 6 characters), and that is not safe site-wide.
- **Real findings:** two `@font-face` rules for **Inter** ship in the CSS but no text uses them (not downloaded, just dead CSS). The ✓ and ⤢ characters on /en/ and → ↗ on the demo are not in the fonts, so they render in a system font. The demo shares one stylesheet across themes, so it declares **7 families it never uses** on this page.
- The French page needs only 3 of the 4 files (no italic), 100.3 KB.
- **marvin.demarkstudio.ca loads no web fonts at all** (no `@font-face`, 0 bytes).

As a CI budget (exit code 1 when exceeded; output trimmed to the end):

```
$ python -m web_font_audit https://demarkstudio.ca/en/ --max-font-bytes 120KB --max-fonts 4 --fail-on declared-unused --no-subset
auditing https://demarkstudio.ca/en/
[...]
Budget exceeded:

- font bytes 139863 > budget 120000
- declared-unused: @font-face declared but not used on this page: Inter.
budget exceeded on 1 page(s)
$ echo $?
1
```

Tests run offline against local HTTP servers, with fonts generated by fontTools:

```
$ python -m pytest -q
...........................                                              [100%]
27 passed in 15.87s
```

## Options

```
web-font-audit URL [URL ...] [--format markdown|json] [--md-out FILE] [--json-out FILE]
               [--max-font-bytes SIZE] [--max-fonts N] [--max-families N] [--fail-on CODES]
               [--no-subset] [--delay 1] [--timeout 30] [--viewport 1366x768] [--user-agent UA]
```

- `--max-font-bytes 150KB` (KB = 1000, KiB = 1024), `--max-fonts`, `--max-families`: per-page budgets.
- `--fail-on font-display,legacy-format` fails on those finding codes; `--fail-on warning` fails on any warning or error.
- Exit codes: `0` ok, `1` budget exceeded, `2` a page could not be loaded.
- Only the URLs given are loaded (no crawling), one at a time and `--delay` seconds apart. The tool itself only sends GET requests; the page's own scripts run as in a normal visit, but nothing is clicked or submitted. User-Agent: `web-font-audit/1.0 (+https://github.com/dreadmoreeee/web-font-audit)`.

[examples/github-actions.yml](examples/github-actions.yml) runs it as a scheduled font budget in GitHub Actions.

From Python:

```python
from web_font_audit import audit

for page in audit(["https://example.com/"]):
    print(page.total_transfer, [f.code for f in page.findings])
```

## Limitations

- "Which face renders this character" is worked out from computed styles and CSS matching rules, not read from the rendering engine. It is right for normal pages; `font-synthesis`, `font-variant` alternates and text inside shadow DOM or iframes are not modelled.
- "Above the fold" is element boxes intersecting the first viewport (default 1366x768), without scrolling.
- Fonts added from JavaScript with `new FontFace(...)` are counted as downloads but have no `@font-face` rule to report.
- Google Fonts and some CDNs choose formats from the User-Agent; with the default User-Agent they may serve something a real browser would not get. Use `--user-agent` with a browser string to compare.
- First- vs third-party uses the last two host labels (three for `co.uk`-style names), not the full Public Suffix List.
- EOT files are reported but not parsed. Transfer sizes include response headers and come from Chromium; a warm cache or HTTP/3 can change them.

## Author

Marvin Palencia, founder of [DeMark Studio](https://demarkstudio.ca), Miramichi, New Brunswick, Canada. Portfolio: [marvin.demarkstudio.ca](https://marvin.demarkstudio.ca)

MIT License.
