"""Turn collected page data into a per-page, per-font report with findings."""

from __future__ import annotations

import base64
from dataclasses import dataclass, field
from typing import Callable
from urllib.parse import unquote_to_bytes, urlsplit

from . import fonts as fonts_mod
from .collect import FontResponse, PageData
from .css import FontFace, is_google_fonts_css, parse_family_list

SECOND_LEVEL = {"co", "com", "org", "net", "gov", "ac", "edu", "gc", "qc", "on"}
FOIT_DISPLAYS = {"auto", "block"}
SEVERITIES = ("error", "warning", "info")
FINDING_CODES = (
    "font-display", "legacy-format", "unused-preload", "preload-crossorigin",
    "missing-preload", "loaded-unused", "declared-unused", "subset",
    "third-party", "missing-glyphs", "load-error", "google-fonts",
)


@dataclass
class Finding:
    code: str
    severity: str
    message: str
    fix: str
    url: str = ""

    def to_dict(self):
        return {"code": self.code, "severity": self.severity, "message": self.message,
                "fix": self.fix, "url": self.url or None}


@dataclass
class FontReport:
    url: str
    format: str
    party: str
    status: int
    transfer_bytes: int
    decoded_bytes: int
    requests: int = 1
    families: list[str] = field(default_factory=list)
    faces: list[FontFace] = field(default_factory=list)
    font_display: list[str] = field(default_factory=list)
    preloaded: bool = False
    used_chars: set[int] = field(default_factory=set)
    above_chars: set[int] = field(default_factory=set)
    missing_chars: set[int] = field(default_factory=set)
    glyphs: int | None = None
    cmap_size: int | None = None
    font_name: str = ""
    variable: bool = False
    parse_error: str = ""
    subset: dict | None = None
    woff2_bytes: int | None = None

    @property
    def used(self) -> bool:
        return bool(self.used_chars)

    def to_dict(self):
        return {
            "url": _short(self.url),
            "format": self.format,
            "party": self.party,
            "status": self.status,
            "transfer_bytes": self.transfer_bytes,
            "decoded_bytes": self.decoded_bytes,
            "requests": self.requests,
            "families": self.families,
            "weights_styles": sorted({f"{f.weight_text()} {f.style}" for f in self.faces}),
            "font_display": self.font_display,
            "preloaded": self.preloaded,
            "used_chars": len(self.used_chars),
            "above_fold_chars": len(self.above_chars),
            "missing_chars": "".join(sorted(chr(c) for c in self.missing_chars))[:80] or None,
            "glyphs": self.glyphs,
            "cmap_codepoints": self.cmap_size,
            "font_name": self.font_name or None,
            "variable": self.variable,
            "parse_error": self.parse_error or None,
            "subset": self.subset,
            "woff2_bytes": self.woff2_bytes,
        }


@dataclass
class PageReport:
    url: str
    final_url: str = ""
    status: int | None = None
    error: str = ""
    viewport: tuple[int, int] = (0, 0)
    fonts: list[FontReport] = field(default_factory=list)
    faces: list[FontFace] = field(default_factory=list)
    face_used: dict[int, bool] = field(default_factory=dict)
    preloads: list[dict] = field(default_factory=list)
    findings: list[Finding] = field(default_factory=list)
    budget_failures: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    subset_flavor: str = ""

    @property
    def total_transfer(self) -> int:
        return sum(f.transfer_bytes for f in self.fonts if f.party != "inline")

    @property
    def total_decoded(self) -> int:
        return sum(f.decoded_bytes for f in self.fonts)

    @property
    def network_fonts(self) -> list[FontReport]:
        return [f for f in self.fonts if f.party != "inline"]

    def used_families(self) -> list[str]:
        out = []
        for f in self.fonts:
            if f.used:
                for fam in f.families:
                    if fam not in out:
                        out.append(fam)
        return out

    def used_variants(self) -> list[str]:
        out = set()
        for f in self.fonts:
            if f.used:
                for face in f.faces:
                    out.add(f"{face.family} {face.weight_text()} {face.style}")
        return sorted(out)

    def to_dict(self):
        return {
            "url": self.url,
            "final_url": self.final_url or None,
            "status": self.status,
            "error": self.error or None,
            "viewport": list(self.viewport),
            "totals": {
                "font_files": len(self.network_fonts),
                "inline_fonts": len(self.fonts) - len(self.network_fonts),
                "transfer_bytes": self.total_transfer,
                "decoded_bytes": self.total_decoded,
                "families": self.used_families(),
                "variants": self.used_variants(),
                "first_party": sum(1 for f in self.fonts if f.party == "first-party"),
                "third_party": sum(1 for f in self.fonts if f.party == "third-party"),
            },
            "fonts": [f.to_dict() for f in self.fonts],
            "font_faces": [
                dict(face.to_dict(), used=self.face_used.get(face.order, False))
                for face in self.faces
            ],
            "preloads": self.preloads,
            "findings": [f.to_dict() for f in self.findings],
            "budget_failures": self.budget_failures,
            "notes": self.notes,
            "subset_flavor": self.subset_flavor,
        }


def _short(url: str) -> str:
    if url.startswith("data:"):
        return url[:40] + "..."
    return url


def site_of(host: str) -> str:
    """Approximate registrable domain: last two labels (three for co.uk-style)."""
    labels = [p for p in (host or "").lower().split(".") if p]
    if len(labels) >= 3 and labels[-2] in SECOND_LEVEL and len(labels[-1]) == 2:
        return ".".join(labels[-3:])
    return ".".join(labels[-2:])


def party_of(font_url: str, page_url: str) -> str:
    if font_url.startswith("data:"):
        return "inline"
    a, b = urlsplit(font_url).hostname or "", urlsplit(page_url).hostname or ""
    return "first-party" if site_of(a) == site_of(b) else "third-party"


def decode_data_url(url: str) -> bytes:
    header, _, payload = url.partition(",")
    if header.endswith(";base64"):
        return base64.b64decode(payload + "=" * (-len(payload) % 4))
    return unquote_to_bytes(payload)


# ---------------------------------------------------------------- matching

def _style_order(style: str) -> list[str]:
    style = style.split()[0].lower() if style else "normal"
    if style == "italic":
        return ["italic", "oblique", "normal"]
    if style == "oblique":
        return ["oblique", "italic", "normal"]
    return ["normal", "oblique", "italic"]


def _weight_distance(desired: int, face_range: tuple[int, int]) -> tuple:
    """Sort key following the CSS Fonts 4 weight matching order."""
    lo, hi = face_range
    if lo <= desired <= hi:
        return (0, 0)
    if 400 <= desired <= 500:
        if desired < lo <= 500:
            return (1, lo - desired)
        if hi < desired:
            return (2, desired - hi)
        return (3, lo - desired)
    if desired < 400:
        if hi < desired:
            return (1, desired - hi)
        return (2, lo - desired)
    if lo > desired:
        return (1, lo - desired)
    return (2, desired - hi)


def match_faces(faces: list[FontFace], weight: int, style: str) -> list[FontFace]:
    """The faces of one family the browser would pick for weight/style, i.e.
    one descriptor set, possibly split by unicode-range. Later rules first."""
    if not faces:
        return []
    for wanted in _style_order(style):
        candidates = [f for f in faces if f.style == wanted]
        if candidates:
            break
    best = min(_weight_distance(weight, f.weight) for f in candidates)
    chosen = [f for f in candidates if _weight_distance(weight, f.weight) == best]
    target = min(chosen, key=lambda f: (f.weight[0] - weight) ** 2).weight
    return sorted((f for f in chosen if f.weight == target), key=lambda f: -f.order)


def _to_int_weight(value) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return 400


# ---------------------------------------------------------------- analysis

class Analyzer:
    def __init__(self, decompress: Callable[[bytes], bytes] | None = None, subset: bool = True):
        self.decompress = decompress
        self.do_subset = subset
        self.flavor = fonts_mod.output_flavor()
        self.latin = fonts_mod.latin_codepoints()

    def analyze(self, data: PageData) -> PageReport:
        report = PageReport(url=data.url, final_url=data.final_url, status=data.status,
                            error=data.error, viewport=data.viewport, notes=list(data.notes),
                            subset_flavor=self.flavor)
        if data.error:
            return report
        page_url = data.final_url or data.url
        report.faces = data.faces
        report.preloads = data.preloads

        # font files: network responses plus inline data: URLs referenced by faces
        files: dict[str, FontReport] = {}
        for resp in data.fonts:
            files[resp.url] = self._font_report(resp, page_url)
        face_file: dict[int, FontReport] = {}
        for face in data.faces:
            for src_url in face.urls:
                if src_url in files:
                    face_file[face.order] = files[src_url]
                    break
                if src_url.startswith("data:"):
                    try:
                        body = decode_data_url(src_url)
                    except Exception:
                        continue
                    resp = FontResponse(src_url, 200, "", 0, len(body), body)
                    files[src_url] = self._font_report(resp, page_url)
                    face_file[face.order] = files[src_url]
                    break
        for order, fr in face_file.items():
            face = next(f for f in data.faces if f.order == order)
            fr.faces.append(face)
            if face.family not in fr.families:
                fr.families.append(face.family)
            display = face.display if face.display_declared else "(not set)"
            if display not in fr.font_display:
                fr.font_display.append(display)

        cmaps = {}
        parsed = {}
        for url, fr in files.items():
            body = self._body_for(url, data)
            if not body:
                continue
            try:
                font = fonts_mod.parse_font(body, self.decompress)
            except Exception as exc:
                fr.parse_error = str(exc) or exc.__class__.__name__
                continue
            parsed[url] = font
            cmaps[url] = font.cmap
            fr.glyphs, fr.cmap_size = font.glyphs, len(font.cmap)
            fr.font_name, fr.variable = font.name, font.variable

        # attribute rendered characters to faces
        by_family: dict[str, list[FontFace]] = {}
        for face in data.faces:
            by_family.setdefault(face.family_key, []).append(face)
        face_chars: dict[int, set[int]] = {}
        face_above: dict[int, set[int]] = {}
        for item in data.usage:
            stack = parse_family_list(item["family"])
            weight = _to_int_weight(item["weight"])
            above = {ord(c) for c in item["above"]}
            chain = []
            for fam in stack:
                if fam not in by_family:
                    # a system or generic font: assume it covers what is left
                    break
                chain.append(match_faces(by_family[fam], weight, item["style"]))
            for ch in item["chars"]:
                cp = ord(ch)
                for matched in chain:
                    face = next((f for f in matched if f.covers(cp)), None)
                    if face is None:
                        continue
                    fr = face_file.get(face.order)
                    if fr is not None and fr.url in cmaps and cp not in cmaps[fr.url]:
                        if not ch.isspace():
                            fr.missing_chars.add(cp)
                        continue
                    face_chars.setdefault(face.order, set()).add(cp)
                    if cp in above:
                        face_above.setdefault(face.order, set()).add(cp)
                    break
        for face in data.faces:
            report.face_used[face.order] = bool(face_chars.get(face.order))
            fr = face_file.get(face.order)
            if fr is not None:
                fr.used_chars |= face_chars.get(face.order, set())
                fr.above_chars |= face_above.get(face.order, set())

        preload_urls = {p["href"].split("#")[0] for p in data.preloads}
        for fr in files.values():
            fr.preloaded = fr.url in preload_urls
            fr.missing_chars -= fr.used_chars
            if self.do_subset and fr.url in parsed and fr.used:
                self._subset(fr, parsed[fr.url])

        # keep files that were downloaded, or inline ones that are used
        report.fonts = sorted(
            (f for f in files.values() if f.party != "inline" or f.used),
            key=lambda f: -f.transfer_bytes,
        )
        report.findings = self._findings(report, data, face_file)
        return report

    def _body_for(self, url: str, data: PageData) -> bytes:
        if url.startswith("data:"):
            try:
                return decode_data_url(url)
            except Exception:
                return b""
        for resp in data.fonts:
            if resp.url == url:
                return resp.body
        return b""

    def _font_report(self, resp: FontResponse, page_url: str) -> FontReport:
        return FontReport(
            url=resp.url,
            format=fonts_mod.detect_format(resp.body) if resp.body else "unknown",
            party=party_of(resp.url, page_url),
            status=resp.status,
            transfer_bytes=resp.transfer_bytes,
            decoded_bytes=resp.decoded_bytes,
            requests=resp.requests,
        )

    def _subset(self, fr: FontReport, font: fonts_mod.ParsedFont):
        flavor = self.flavor
        try:
            if font.format == flavor:
                reference = fr.decoded_bytes
            else:
                reference = len(fonts_mod.encode(font.sfnt, flavor))
            page_set = fr.used_chars & font.cmap
            latin_set = (self.latin | fr.used_chars) & font.cmap
            page_size = len(fonts_mod.subset(font.sfnt, page_set, flavor))
            latin_size = len(fonts_mod.subset(font.sfnt, latin_set, flavor))
            if flavor == "woff2" and font.format != "woff2":
                fr.woff2_bytes = reference
        except Exception as exc:
            fr.parse_error = f"subset failed: {exc}"
            return
        scale = fr.decoded_bytes / reference if reference else 1.0
        fr.subset = {
            "measured_as": flavor,
            "reference_bytes": reference,
            "page_subset_bytes": page_size,
            "page_subset_codepoints": len(page_set),
            "latin_subset_bytes": latin_size,
            "latin_subset_codepoints": len(latin_set),
            "estimated": font.format != flavor,
            "page_subset_estimate": round(page_size * scale),
            "latin_subset_estimate": round(latin_size * scale),
            "latin_saving_bytes": max(0, fr.decoded_bytes - round(latin_size * scale)),
        }

    # ------------------------------------------------------------ findings

    def _findings(self, report: PageReport, data: PageData, face_file) -> list[Finding]:
        out: list[Finding] = []
        used_orders = {o for o, used in report.face_used.items() if used}

        for fr in report.fonts:
            name = fr.families[0] if fr.families else _file_name(fr.url)
            if fr.status >= 400:
                out.append(Finding("load-error", "error",
                                   f"{_file_name(fr.url)} returned HTTP {fr.status}.",
                                   "Fix the URL in the @font-face src or restore the file.", fr.url))
                continue
            if fr.format in fonts_mod.LEGACY_FORMATS:
                extra = ""
                if fr.woff2_bytes:
                    extra = f" Measured as WOFF2: {kb(fr.woff2_bytes)} (now {kb(fr.decoded_bytes)})."
                out.append(Finding("legacy-format", "warning",
                                   f"{name} is served as {fr.format.upper()}, not WOFF2.{extra}",
                                   "Convert to WOFF2 (e.g. `fonttools ttLib.woff2 compress`) and list it "
                                   "first in src with format(\"woff2\"); every current browser supports it.",
                                   fr.url))
            if not fr.used and fr.party != "inline":
                why = " It is preloaded." if fr.preloaded else ""
                out.append(Finding("loaded-unused", "warning",
                                   f"{_file_name(fr.url)} ({kb(fr.transfer_bytes)}) was downloaded but no "
                                   f"visible text on this page renders with it.{why}",
                                   "Remove the preload or @font-face that pulls it in, or load it only on "
                                   "pages that use it.", fr.url))
            if fr.used and any(d in FOIT_DISPLAYS or d == "(not set)" for d in fr.font_display):
                shown = ", ".join(fr.font_display)
                fix = "Add `font-display: swap;` (or `optional` for body text) to the @font-face rule."
                if any(is_google_fonts_css(face.stylesheet) for face in fr.faces):
                    fix = "Add `&display=swap` to the Google Fonts CSS URL."
                out.append(Finding("font-display", "warning",
                                   f"{name}: font-display is {shown}; text using it stays invisible for "
                                   "up to 3 s while the font loads (FOIT).", fix, fr.url))
            if fr.party == "third-party":
                out.append(Finding("third-party", "info",
                                   f"{name} is loaded from {urlsplit(fr.url).hostname}, which costs an "
                                   "extra connection and shares visitor IPs with that host.",
                                   "Self-host the font files on your own domain.", fr.url))
            if fr.missing_chars:
                sample = "".join(sorted(chr(c) for c in fr.missing_chars))[:30]
                out.append(Finding("missing-glyphs", "info",
                                   f"{name}: {len(fr.missing_chars)} rendered character(s) are not in the "
                                   f"font and fall back to another font: {sample!r}",
                                   "Use a font build that covers these characters, or accept the fallback.",
                                   fr.url))
            if fr.subset and fr.used:
                saving = fr.subset["latin_saving_bytes"]
                if saving >= 2000 and saving >= 0.10 * fr.decoded_bytes:
                    approx = "about " if fr.subset["estimated"] else ""
                    out.append(Finding("subset", "info",
                                       f"{name}: subsetting to Latin (plus this page's characters) saves "
                                       f"{approx}{kb(saving)} of {kb(fr.decoded_bytes)} "
                                       f"({fr.cmap_size} code points in the font, "
                                       f"{fr.subset['latin_subset_codepoints']} kept).",
                                       "Subset with `pyftsubset font.ttf --unicodes=U+0000-00FF,U+0131,"
                                       "U+0152-0153,U+2000-206F,U+20AC,U+2122 --flavor=woff2`, or split it "
                                       "with unicode-range.", fr.url))

        font_urls = {fr.url: fr for fr in report.fonts}
        for pre in data.preloads:
            href = pre["href"].split("#")[0]
            fr = font_urls.get(href)
            if fr is None or not fr.used:
                referenced = any(href in face.urls for face in data.faces)
                why = ("no @font-face rule uses this URL" if not referenced
                       else "no visible text on this page uses its font")
                out.append(Finding("unused-preload", "warning",
                                   f"Preloaded {_file_name(href)} but {why}.",
                                   "Remove this <link rel=\"preload\" as=\"font\">, or point it at the "
                                   "exact URL the @font-face src uses.", href))
            if not pre["crossorigin"]:
                double = fr is not None and fr.requests > 1
                note = " The file was downloaded twice." if double else ""
                out.append(Finding("preload-crossorigin", "warning",
                                   f"Preload of {_file_name(href)} has no crossorigin attribute, so the "
                                   f"browser cannot reuse it for @font-face.{note}",
                                   "Add `crossorigin` to the <link rel=\"preload\" as=\"font\"> tag.", href))

        critical = [fr for fr in report.fonts if fr.above_chars and not fr.preloaded
                    and fr.party != "inline" and fr.status < 400]
        critical.sort(key=lambda f: -len(f.above_chars))
        for fr in critical[:2]:
            name = fr.families[0] if fr.families else _file_name(fr.url)
            href = _href(fr.url, report.final_url or report.url)
            out.append(Finding("missing-preload", "info",
                               f"{name} renders text above the fold ({len(fr.above_chars)} distinct "
                               "characters) but is not preloaded; the browser finds it only after the CSS "
                               "is parsed.",
                               f"Add `<link rel=\"preload\" href=\"{href}\" as=\"font\" "
                               f"type=\"font/{fr.format}\" crossorigin>` for the one or two most "
                               "important fonts only.", fr.url))

        unused_families = sorted({f.family for f in data.faces} -
                                 {f.family for f in data.faces if f.order in used_orders})
        if unused_families:
            out.append(Finding("declared-unused", "info",
                               f"@font-face declared but not used on this page: {', '.join(unused_families)}.",
                               "Remove unused @font-face rules or move them to the pages that use them.",
                               ""))
        if any(is_google_fonts_css(f.stylesheet) for f in data.faces):
            out.append(Finding("google-fonts", "info",
                               "Fonts come from the Google Fonts CSS API, which serves formats based on "
                               "the User-Agent; results may differ for real browsers.",
                               "Self-host the WOFF2 files, or re-run with a browser --user-agent.", ""))
        order = {s: i for i, s in enumerate(SEVERITIES)}
        codes = {c: i for i, c in enumerate(FINDING_CODES)}
        out.sort(key=lambda f: (order[f.severity], codes[f.code]))
        return out


def _file_name(url: str) -> str:
    if url.startswith("data:"):
        return "inline data: font"
    path = urlsplit(url).path
    return path.rsplit("/", 1)[-1] or url


def _href(url: str, page_url: str) -> str:
    """Path-only href for files on the page's own origin, full URL otherwise."""
    parts = urlsplit(url)
    if parts.netloc != urlsplit(page_url).netloc:
        return url
    return parts.path + ("?" + parts.query if parts.query else "")


def kb(n: int | None) -> str:
    if n is None:
        return "-"
    return f"{n / 1000:.1f} KB"


# ---------------------------------------------------------------- budgets

def check_budgets(report: PageReport, max_font_bytes=None, max_fonts=None,
                  max_families=None, fail_on=()) -> list[str]:
    failures = []
    if report.error:
        return failures
    if max_font_bytes is not None and report.total_transfer > max_font_bytes:
        failures.append(f"font bytes {report.total_transfer} > budget {max_font_bytes}")
    if max_fonts is not None and len(report.network_fonts) > max_fonts:
        failures.append(f"font files {len(report.network_fonts)} > budget {max_fonts}")
    if max_families is not None and len(report.used_families()) > max_families:
        failures.append(f"families {len(report.used_families())} > budget {max_families}")
    wanted = set(fail_on)
    for finding in report.findings:
        if finding.code in wanted or finding.severity in wanted:
            failures.append(f"{finding.code}: {finding.message}")
    return failures
