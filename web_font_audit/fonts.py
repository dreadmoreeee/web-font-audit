"""Font file inspection and in-memory subsetting with fontTools."""

from __future__ import annotations

import io
import logging
import threading
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Callable

from fontTools import subset as ft_subset
from fontTools.ttLib import TTFont
from fontTools.ttLib import woff2 as ft_woff2

logging.getLogger("fontTools").setLevel(logging.ERROR)

LEGACY_FORMATS = {"woff", "ttf", "otf", "eot", "ttc"}

# Same code points as the "latin" subset Google Fonts serves.
LATIN_RANGES = [
    (0x0000, 0x00FF), (0x0131, 0x0131), (0x0152, 0x0153), (0x02BB, 0x02BC),
    (0x02C6, 0x02C6), (0x02DA, 0x02DA), (0x02DC, 0x02DC), (0x0304, 0x0304),
    (0x0308, 0x0308), (0x0329, 0x0329), (0x2000, 0x206F), (0x20AC, 0x20AC),
    (0x2122, 0x2122), (0x2191, 0x2191), (0x2193, 0x2193), (0x2212, 0x2212),
    (0x2215, 0x2215), (0xFEFF, 0xFEFF), (0xFFFD, 0xFFFD),
]


def latin_codepoints() -> set[int]:
    out: set[int] = set()
    for lo, hi in LATIN_RANGES:
        out.update(range(lo, hi + 1))
    return out


def detect_format(data: bytes) -> str:
    head = data[:4]
    if head == b"wOF2":
        return "woff2"
    if head == b"wOFF":
        return "woff"
    if head == b"OTTO":
        return "otf"
    if head in (b"\x00\x01\x00\x00", b"true"):
        return "ttf"
    if head == b"ttcf":
        return "ttc"
    if len(data) >= 36 and data[34:36] == b"LP":
        return "eot"
    return "unknown"


def brotli_module():
    """The brotli (or brotlicffi) module if installed, else None."""
    try:
        import brotlicffi as mod  # type: ignore
        return mod
    except ImportError:
        pass
    try:
        import brotli as mod  # type: ignore
        return mod
    except ImportError:
        return None


class _DecompressOnly:
    """Stands in for the brotli module when only decompression is available."""

    MODE_GENERIC, MODE_TEXT, MODE_FONT = 0, 1, 2

    def __init__(self, decompress: Callable[[bytes], bytes]):
        self.decompress = decompress

    def compress(self, *args, **kwargs):
        raise ImportError("brotli compression is not available")


_patch_lock = threading.Lock()


@contextmanager
def woff2_brotli(module):
    """Temporarily give fontTools' WOFF2 code a brotli implementation."""
    with _patch_lock:
        saved = (ft_woff2.haveBrotli, getattr(ft_woff2, "brotli", None))
        ft_woff2.haveBrotli = True
        ft_woff2.brotli = module
        try:
            yield
        finally:
            ft_woff2.haveBrotli = saved[0]
            if saved[1] is None:
                del ft_woff2.brotli
            else:
                ft_woff2.brotli = saved[1]


@dataclass
class ParsedFont:
    format: str
    sfnt: bytes  # uncompressed OpenType data
    cmap: set[int] = field(default_factory=set)
    glyphs: int = 0
    name: str = ""
    variable: bool = False


def parse_font(data: bytes, decompress: Callable[[bytes], bytes] | None = None) -> ParsedFont:
    """Parse TTF/OTF/WOFF/WOFF2 bytes. `decompress` is a brotli decoder used for
    WOFF2 when the brotli module is not installed."""
    fmt = detect_format(data)
    if fmt in ("eot", "unknown", "ttc"):
        raise ValueError(f"cannot parse {fmt} font data")
    if fmt == "woff2" and not ft_woff2.haveBrotli:
        if decompress is None:
            raise ValueError("WOFF2 needs brotli to parse")
        with woff2_brotli(_DecompressOnly(decompress)):
            font = TTFont(io.BytesIO(data), lazy=False)
            font.flavor = None
            buf = io.BytesIO()
            font.save(buf)
    else:
        font = TTFont(io.BytesIO(data), lazy=False)
        font.flavor = None
        buf = io.BytesIO()
        font.save(buf)
    cmap = font.getBestCmap() or {}
    name = ""
    if "name" in font:
        name = font["name"].getBestFullName() or font["name"].getBestFamilyName() or ""
    return ParsedFont(
        format=fmt,
        sfnt=buf.getvalue(),
        cmap=set(cmap),
        glyphs=len(font.getGlyphOrder()),
        name=name,
        variable="fvar" in font,
    )


def output_flavor() -> str:
    """woff2 when brotli can compress, otherwise woff (zlib)."""
    return "woff2" if brotli_module() is not None else "woff"


def encode(sfnt: bytes, flavor: str) -> bytes:
    font = TTFont(io.BytesIO(sfnt))
    font.flavor = flavor
    buf = io.BytesIO()
    font.save(buf)
    return buf.getvalue()


def subset(sfnt: bytes, unicodes: set[int], flavor: str) -> bytes:
    """Drop code points only: every OpenType feature, name, hint and table is
    kept, so the size difference is what subsetting alone saves."""
    options = ft_subset.Options()
    options.flavor = flavor
    options.notdef_outline = True
    options.layout_features = ["*"]
    options.name_IDs = ["*"]
    options.name_languages = ["*"]
    options.name_legacy = True
    options.glyph_names = True
    options.legacy_kern = True
    options.symbol_cmap = True
    options.hinting = True
    options.passthrough_tables = True
    options.drop_tables = []
    font = TTFont(io.BytesIO(sfnt))
    subsetter = ft_subset.Subsetter(options=options)
    subsetter.populate(unicodes=sorted(unicodes))
    subsetter.subset(font)
    font.flavor = flavor
    buf = io.BytesIO()
    font.save(buf)
    return buf.getvalue()
