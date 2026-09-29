"""Small, forgiving parser for the parts of CSS that matter for web fonts.

Only @font-face rules and @import are understood; everything else is skipped.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from urllib.parse import urljoin

_COMMENT = re.compile(r"/\*.*?\*/", re.S)
_FONT_FACE = re.compile(r"@font-face\s*\{", re.I)
_IMPORT = re.compile(r"@import\s+(?:url\(\s*)?(['\"]?)([^'\")\s;]+)\1\s*\)?[^;]*;", re.I)


@dataclass
class Source:
    kind: str  # "url" or "local"
    value: str  # absolute URL or local font name
    format: str = ""


@dataclass
class FontFace:
    family: str
    sources: list[Source] = field(default_factory=list)
    display: str = "auto"
    display_declared: bool = False
    unicode_range: list[tuple[int, int]] | None = None
    unicode_range_text: str = ""
    weight: tuple[int, int] = (400, 400)
    style: str = "normal"
    stylesheet: str = ""  # URL of the stylesheet, or page URL for inline <style>
    order: int = 0

    @property
    def family_key(self) -> str:
        return self.family.lower()

    @property
    def urls(self) -> list[str]:
        return [s.value for s in self.sources if s.kind == "url"]

    @property
    def local_names(self) -> list[str]:
        return [s.value for s in self.sources if s.kind == "local"]

    def covers(self, codepoint: int) -> bool:
        if self.unicode_range is None:
            return True
        return any(lo <= codepoint <= hi for lo, hi in self.unicode_range)

    def weight_text(self) -> str:
        lo, hi = self.weight
        return str(lo) if lo == hi else f"{lo} {hi}"

    def to_dict(self) -> dict:
        return {
            "family": self.family,
            "weight": self.weight_text(),
            "style": self.style,
            "font_display": self.display if self.display_declared else None,
            "unicode_range": self.unicode_range_text or None,
            "local_sources": self.local_names,
            "url_sources": [
                {"url": _short_data(s.value), "format": s.format or None}
                for s in self.sources if s.kind == "url"
            ],
            "stylesheet": self.stylesheet,
        }


def _short_data(url: str) -> str:
    if url.startswith("data:"):
        return url[:40] + "...(%d chars)" % len(url)
    return url


def strip_comments(css: str) -> str:
    return _COMMENT.sub("", css)


def split_top(text: str, sep: str) -> list[str]:
    """Split on `sep` outside quotes and parentheses."""
    parts, buf, depth, quote = [], [], 0, ""
    i = 0
    while i < len(text):
        ch = text[i]
        if quote:
            buf.append(ch)
            if ch == "\\" and i + 1 < len(text):
                buf.append(text[i + 1])
                i += 1
            elif ch == quote:
                quote = ""
        elif ch in "'\"":
            quote = ch
            buf.append(ch)
        elif ch == "(":
            depth += 1
            buf.append(ch)
        elif ch == ")":
            depth = max(0, depth - 1)
            buf.append(ch)
        elif ch == sep and depth == 0:
            parts.append("".join(buf))
            buf = []
        else:
            buf.append(ch)
        i += 1
    parts.append("".join(buf))
    return [p.strip() for p in parts if p.strip()]


def unquote(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "'\"":
        value = value[1:-1]
    return re.sub(r"\\(.)", r"\1", value)


def parse_family_list(value: str) -> list[str]:
    """'"Open Sans", Arial, sans-serif' -> ['open sans', 'arial', 'sans-serif']."""
    out = []
    for part in split_top(value, ","):
        name = unquote(part)
        name = " ".join(name.split())
        if name:
            out.append(name.lower())
    return out


def parse_unicode_range(value: str) -> list[tuple[int, int]]:
    ranges = []
    for token in value.split(","):
        token = token.strip().upper()
        if not token.startswith("U+"):
            continue
        body = token[2:]
        try:
            if "-" in body:
                lo, hi = body.split("-", 1)
                ranges.append((int(lo, 16), int(hi, 16)))
            elif "?" in body:
                ranges.append((int(body.replace("?", "0"), 16), int(body.replace("?", "F"), 16)))
            else:
                cp = int(body, 16)
                ranges.append((cp, cp))
        except ValueError:
            continue
    return ranges


def _weight_value(token: str) -> int:
    token = token.strip().lower()
    if token in ("normal", "auto", ""):
        return 400
    if token == "bold":
        return 700
    if token == "lighter":
        return 300
    if token == "bolder":
        return 700
    try:
        return int(float(token))
    except ValueError:
        return 400


def parse_weight(value: str) -> tuple[int, int]:
    tokens = value.split()
    if not tokens:
        return (400, 400)
    lo = _weight_value(tokens[0])
    hi = _weight_value(tokens[1]) if len(tokens) > 1 else lo
    return (min(lo, hi), max(lo, hi))


def parse_style(value: str) -> str:
    value = value.strip().lower()
    if value.startswith("italic"):
        return "italic"
    if value.startswith("oblique"):
        return "oblique"
    return "normal"


def parse_src(value: str, base_url: str) -> list[Source]:
    sources = []
    for item in split_top(value, ","):
        m = re.match(r"(url|local)\(\s*(.*?)\s*\)(.*)$", item, re.I | re.S)
        if not m:
            continue
        kind, arg, rest = m.group(1).lower(), unquote(m.group(2)), m.group(3)
        if kind == "local":
            sources.append(Source("local", arg))
            continue
        fm = re.search(r"format\(\s*(['\"]?)([^'\")]+)\1\s*\)", rest, re.I)
        fmt = fm.group(2).strip().lower() if fm else ""
        url = arg if arg.startswith("data:") else urljoin(base_url, arg)
        sources.append(Source("url", url.split("#")[0] if not url.startswith("data:") else url, fmt))
    return sources


def _block_end(css: str, start: int) -> int:
    """Index of the '}' that closes the block whose body starts at `start`."""
    depth, quote, i = 1, "", start
    while i < len(css):
        ch = css[i]
        if quote:
            if ch == "\\":
                i += 1
            elif ch == quote:
                quote = ""
        elif ch in "'\"":
            quote = ch
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return i
        i += 1
    return len(css)


def parse_font_face_body(body: str, base_url: str) -> FontFace | None:
    decls = {}
    for decl in split_top(body, ";"):
        if ":" not in decl:
            continue
        name, value = decl.split(":", 1)
        decls[name.strip().lower()] = value.strip()
    family = unquote(decls.get("font-family", ""))
    if not family:
        return None
    face = FontFace(family=" ".join(family.split()))
    face.sources = parse_src(decls.get("src", ""), base_url)
    if "font-display" in decls:
        face.display = decls["font-display"].strip().lower()
        face.display_declared = True
    if "unicode-range" in decls:
        face.unicode_range_text = " ".join(decls["unicode-range"].split())
        face.unicode_range = parse_unicode_range(decls["unicode-range"])
    face.weight = parse_weight(decls.get("font-weight", "normal"))
    face.style = parse_style(decls.get("font-style", "normal"))
    face.stylesheet = base_url
    return face


def parse_font_faces(css: str, base_url: str) -> list[FontFace]:
    """All @font-face rules in a stylesheet, in source order (nested ones too)."""
    css = strip_comments(css)
    faces = []
    for m in _FONT_FACE.finditer(css):
        end = _block_end(css, m.end())
        face = parse_font_face_body(css[m.end():end], base_url)
        if face:
            faces.append(face)
    return faces


def parse_imports(css: str, base_url: str) -> list[str]:
    return [urljoin(base_url, m.group(2)) for m in _IMPORT.finditer(strip_comments(css))]


def is_google_fonts_css(url: str) -> bool:
    return "fonts.googleapis.com/css" in url
