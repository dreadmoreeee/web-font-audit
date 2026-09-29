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

## https://demarkstudio.ca/fr/conception-web/miramichi

HTTP 200, viewport 1366x768. 3 font file(s), 100.3 KB transferred (99.2 KB decoded); 3 family(ies), 3 weight/style variant(s) used; 3 first-party, 0 third-party.

| Font file | Family | Variant | Format | Transfer | Party | font-display | Preload | Chars used (above fold) |
|---|---|---|---|---:|---|---|---|---:|
| cormorant-garamond-latin.woff2 | Cormorant Garamond | 400 700 normal | woff2 | 38.0 KB | first-party | swap | yes | 41 (28) |
| jetbrains-mono-latin.woff2 | JetBrains Mono | 400 700 normal | woff2 | 31.9 KB | first-party | swap | yes | 39 (22) |
| instrument-sans-normal-latin.woff2 | Instrument Sans | 400 700 normal | woff2 | 30.5 KB | first-party | swap | yes | 71 (0) |

Subsetting: fontTools subsets built in memory and measured as WOFF, because the brotli package is not installed and WOFF2 cannot be written. For files served in another format, sizes are scaled by subset/original WOFF size (marked ~).

| Font file | Served | Code points in font | Latin subset | Page-only subset |
|---|---:|---:|---:|---:|
| cormorant-garamond-latin.woff2 | 37.6 KB | 229 | ~34.9 KB (224 cp) | ~10.6 KB (41 cp) |
| jetbrains-mono-latin.woff2 | 31.4 KB | 229 | ~30.9 KB (223 cp) | ~4.5 KB (39 cp) |
| instrument-sans-normal-latin.woff2 | 30.1 KB | 208 | ~30.1 KB (204 cp) | ~12.2 KB (71 cp) |

Findings:

- **INFO** `declared-unused` @font-face declared but not used on this page: Inter.
  Fix: Remove unused @font-face rules or move them to the pages that use them.

@font-face rules: 7 (3 used on this page)

| Family | Weight | Style | font-display | unicode-range | local() | Used |
|---|---|---|---|---|---|---|
| Inter | 100 900 | normal | swap | U+0-FF, U+131, U+152-153, U+2BB-2BC, ... | - | no |
| Inter | 100 900 | normal | swap | U+100-2BA, U+2BD-2C5, U+2C7-2CC, U+2C... | - | no |
| Cormorant Garamond | 400 700 | normal | swap | - | - | yes |
| Cormorant Garamond | 400 700 | italic | swap | - | - | no |
| Instrument Sans | 400 700 | normal | swap | - | - | yes |
| Instrument Sans | 400 700 | italic | swap | - | - | no |
| JetBrains Mono | 400 700 | normal | swap | - | - | yes |

Font preloads: cormorant-garamond-latin.woff2, instrument-sans-normal-latin.woff2, jetbrains-mono-latin.woff2

## https://demo.demarkstudio.ca/riverside-pub/site

HTTP 200, viewport 1366x768. 2 font file(s), 118.7 KB transferred (117.6 KB decoded); 2 family(ies), 2 weight/style variant(s) used; 2 first-party, 0 third-party.

| Font file | Family | Variant | Format | Transfer | Party | font-display | Preload | Chars used (above fold) |
|---|---|---|---|---:|---|---|---|---:|
| fraunces-latin.woff2 | Fraunces | 500 700 normal | woff2 | 68.0 KB | first-party | swap | yes | 48 (26) |
| worksans-latin.woff2 | Work Sans | 400 600 normal | woff2 | 50.7 KB | first-party | swap | yes | 63 (51) |

Subsetting: fontTools subsets built in memory and measured as WOFF, because the brotli package is not installed and WOFF2 cannot be written. For files served in another format, sizes are scaled by subset/original WOFF size (marked ~).

| Font file | Served | Code points in font | Latin subset | Page-only subset |
|---|---:|---:|---:|---:|
| fraunces-latin.woff2 | 67.3 KB | 222 | ~67.3 KB (219 cp) | ~25.9 KB (48 cp) |
| worksans-latin.woff2 | 50.3 KB | 232 | ~49.8 KB (226 cp) | ~21.7 KB (63 cp) |

Findings:

- **INFO** `declared-unused` @font-face declared but not used on this page: Barlow Condensed, Bricolage Grotesque, Cormorant Garamond, IBM Plex Sans, Instrument Sans, Inter, JetBrains Mono.
  Fix: Remove unused @font-face rules or move them to the pages that use them.
- **INFO** `missing-glyphs` Work Sans: 2 rendered character(s) are not in the font and fall back to another font: '→↗'
  Fix: Use a font build that covers these characters, or accept the fallback.

@font-face rules: 11 (2 used on this page)

| Family | Weight | Style | font-display | unicode-range | local() | Used |
|---|---|---|---|---|---|---|
| Inter | 100 900 | normal | swap | U+0-FF, U+131, U+152-153, U+2BB-2BC, ... | - | no |
| Inter | 100 900 | normal | swap | U+100-2BA, U+2BD-2C5, U+2C7-2CC, U+2C... | - | no |
| Instrument Sans | 400 700 | normal | swap | - | - | no |
| Fraunces | 500 700 | normal | swap | - | - | yes |
| Work Sans | 400 600 | normal | swap | - | - | yes |
| Cormorant Garamond | 400 700 | normal | swap | - | - | no |
| Cormorant Garamond | 400 700 | italic | swap | - | - | no |
| IBM Plex Sans | 400 700 | normal | swap | - | - | no |
| Bricolage Grotesque | 200 800 | normal | swap | - | - | no |
| Barlow Condensed | 700 | normal | swap | - | - | no |
| JetBrains Mono | 400 700 | normal | swap | - | - | no |

Font preloads: fraunces-latin.woff2, worksans-latin.woff2

## https://marvin.demarkstudio.ca/

HTTP 200, viewport 1366x768. 0 font file(s), 0.0 KB transferred (0.0 KB decoded); 0 family(ies), 0 weight/style variant(s) used; 0 first-party, 0 third-party.

No findings.
