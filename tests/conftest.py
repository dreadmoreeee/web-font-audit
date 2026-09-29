import http.server
import io
import sys
import threading
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fontTools.fontBuilder import FontBuilder  # noqa: E402
from fontTools.pens.ttGlyphPen import TTGlyphPen  # noqa: E402
from fontTools.ttLib import TTFont  # noqa: E402

from web_font_audit.fonts import woff2_brotli  # noqa: E402

# Latin, Greek and Cyrillic: big enough that a Latin subset is clearly smaller.
DEFAULT_CODEPOINTS = (list(range(0x20, 0x7F)) + list(range(0xA0, 0x100))
                      + list(range(0x370, 0x3FF)) + list(range(0x400, 0x500)))


def _glyph(seed):
    pen = TTGlyphPen(None)
    # a few contours whose shape depends on the seed, so glyphs do not compress to nothing
    for k in range(3):
        x0 = 40 + (seed * 7 + k * 53) % 200
        y0 = (seed * 13 + k * 97) % 300
        pen.moveTo((x0, y0))
        pen.lineTo((x0 + 120 + seed % 37, y0 + 10))
        pen.lineTo((x0 + 90, y0 + 400 + (seed * 3) % 91))
        pen.lineTo((x0 + 5, y0 + 300 - k * 17))
        pen.closePath()
    return pen.glyph()


def make_font(family="Test Sans", codepoints=None, flavor=None, style="Regular") -> bytes:
    """A small TrueType font; flavor None (TTF), 'woff' or 'woff2'."""
    codepoints = sorted(set(codepoints or DEFAULT_CODEPOINTS))
    names = [".notdef"] + [f"uni{cp:04X}" for cp in codepoints]
    fb = FontBuilder(1000, isTTF=True)
    fb.setupGlyphOrder(names)
    fb.setupCharacterMap({cp: f"uni{cp:04X}" for cp in codepoints})
    glyphs = {name: _glyph(i) for i, name in enumerate(names)}
    fb.setupGlyf(glyphs)
    fb.setupHorizontalMetrics({name: (600, 40) for name in names})
    fb.setupHorizontalHeader(ascent=800, descent=-200)
    fb.setupNameTable({"familyName": family, "styleName": style})
    fb.setupOS2(sTypoAscender=800, sTypoDescender=-200, usWinAscent=800, usWinDescent=200)
    fb.setupPost()
    buf = io.BytesIO()
    fb.save(buf)
    if flavor is None:
        return buf.getvalue()
    font = TTFont(io.BytesIO(buf.getvalue()))
    font.flavor = flavor
    out = io.BytesIO()
    if flavor == "woff2":
        with woff2_brotli(StoredBrotli):
            font.save(out)
    else:
        font.save(out)
    return out.getvalue()


def brotli_stored(data: bytes) -> bytes:
    """A valid brotli stream made of uncompressed meta-blocks (RFC 7932 9.2)."""
    bits = []

    def put(value, n):
        bits.extend((value >> i) & 1 for i in range(n))

    put(0, 1)  # WBITS = 16
    for pos in range(0, len(data), 65536):
        chunk = data[pos:pos + 65536]
        put(0, 1)  # ISLAST = 0
        put(0, 2)  # MNIBBLES = 4
        put(len(chunk) - 1, 16)
        put(1, 1)  # ISUNCOMPRESSED
        bits.extend([0] * (-len(bits) % 8))
        for b in chunk:
            put(b, 8)
    put(1, 1)  # ISLAST
    put(1, 1)  # ISLASTEMPTY
    bits.extend([0] * (-len(bits) % 8))
    return bytes(sum(bits[i + j] << j for j in range(8)) for i in range(0, len(bits), 8))


def brotli_stored_decode(data: bytes) -> bytes:
    """Decoder for streams written by brotli_stored only."""
    bitpos = 0

    def get(n):
        nonlocal bitpos
        value = 0
        for i in range(n):
            value |= ((data[bitpos >> 3] >> (bitpos & 7)) & 1) << i
            bitpos += 1
        return value

    assert get(1) == 0
    out = bytearray()
    while True:
        if get(1):
            assert get(1) == 1
            return bytes(out)
        assert get(2) == 0
        length = get(16) + 1
        assert get(1) == 1
        bitpos += -bitpos % 8
        start = bitpos >> 3
        out += data[start:start + length]
        bitpos += length * 8


class StoredBrotli:
    MODE_GENERIC, MODE_TEXT, MODE_FONT = 0, 1, 2

    @staticmethod
    def compress(data, **kwargs):
        return brotli_stored(data)

    @staticmethod
    def decompress(data):
        return brotli_stored_decode(data)


CONTENT_TYPES = {
    ".html": "text/html; charset=utf-8", ".css": "text/css", ".woff2": "font/woff2",
    ".woff": "font/woff", ".ttf": "font/ttf", ".otf": "font/otf",
}


class Site:
    """Serves files from memory on 127.0.0.1 (or another host name) on a free port."""

    def __init__(self, host="127.0.0.1"):
        self.files = {}
        self.headers = {}
        self.hits = {}
        site = self

        class Handler(http.server.BaseHTTPRequestHandler):
            def do_GET(self):  # noqa: N802
                path = self.path.split("?")[0]
                site.hits[path] = site.hits.get(path, 0) + 1
                if path not in site.files:
                    self.send_response(404)
                    self.send_header("Content-Length", "0")
                    self.end_headers()
                    return
                body = site.files[path]
                ext = "." + path.rsplit(".", 1)[-1] if "." in path else ".html"
                self.send_response(200)
                self.send_header("Content-Type", CONTENT_TYPES.get(ext, "application/octet-stream"))
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Access-Control-Allow-Origin", "*")
                for k, v in site.headers.get(path, {}).items():
                    self.send_header(k, v)
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *args):
                pass

        self.server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.port = self.server.server_address[1]
        self.base = f"http://{host}:{self.port}"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def add(self, path, body):
        self.files[path] = body.encode("utf-8") if isinstance(body, str) else body

    def url(self, path):
        return self.base + path

    def close(self):
        self.server.shutdown()
        self.server.server_close()


def build_demo_site(site, remote, fontmaker):
    site.add("/fonts/body.ttf", fontmaker("Body"))
    site.add("/fonts/head.woff2", fontmaker("Head", flavor="woff2"))
    site.add("/fonts/below.woff", fontmaker("Below", flavor="woff"))
    site.add("/fonts/icons.ttf", fontmaker("Icons", codepoints=[0x20, 0xE001, 0xE002, 0xE003]))
    site.add("/fonts/never.woff2", fontmaker("Never", flavor="woff2"))
    site.add("/fonts/orphan.woff2", fontmaker("Orphan", flavor="woff2"))
    remote.add("/remote.woff", fontmaker("Remote", flavor="woff"))
    remote.add("/remote.css", f"""
        @font-face {{ font-family: "Remote"; src: url("remote.woff") format("woff");
                      font-display: block; }}
    """)
    site.add("/head.css", """
        @font-face { font-family: 'Head'; font-weight: 700;
                     src: url(/fonts/head.woff2) format('woff2'); font-display: swap; }
        @font-face { font-family: 'Never'; src: url(/fonts/never.woff2) format('woff2');
                     font-display: swap; }
        @font-face { font-family: 'Below'; src: local('Below Font'), url(/fonts/below.woff) format('woff');
                     font-display: fallback; }
        @font-face { font-family: 'Icons'; src: url(/fonts/icons.ttf) format('truetype');
                     font-display: block; unicode-range: U+E000-E0FF; }
    """)
    site.add("/", f"""<!doctype html>
<html><head><meta charset="utf-8"><title>t</title>
<link rel="preload" href="/fonts/head.woff2" as="font" type="font/woff2" crossorigin>
<link rel="preload" href="/fonts/orphan.woff2" as="font" type="font/woff2">
<link rel="stylesheet" href="/head.css">
<link rel="stylesheet" href="{remote.url('/remote.css')}">
<style>
  @font-face {{ font-family: "Body"; src: url("/fonts/body.ttf") format("truetype"); }}
  body {{ font-family: "Body", sans-serif; }}
  h1 {{ font-family: Head, serif; font-weight: 700; }}
  .below {{ font-family: Below; margin-top: 4000px; }}
  .remote {{ font-family: Remote, sans-serif; }}
  .icon::before {{ font-family: Icons; content: "\\e001"; }}
  .hidden {{ display: none; font-family: Never; }}
</style></head>
<body>
<h1>Hello fonts</h1>
<p>Body text here &#x3A9; <span class="icon"></span></p>
<p class="remote">remote</p>
<p class="hidden">never shown</p>
<div class="below">far below the fold</div>
<p>&#x4E2D;</p>
</body></html>""")


@pytest.fixture
def pages(site, remote_site, fontmaker):
    build_demo_site(site, remote_site, fontmaker)
    return site, remote_site


@pytest.fixture
def site():
    s = Site()
    yield s
    s.close()


@pytest.fixture
def remote_site():
    """A second origin (host name localhost) for cross-origin resources."""
    s = Site(host="localhost")
    yield s
    s.close()


@pytest.fixture
def fontmaker():
    return make_font


@pytest.fixture
def stored_brotli():
    return StoredBrotli


@pytest.fixture(scope="module")
def collector():
    from web_font_audit.collect import Collector

    with Collector(timeout=20, settle=0.2) as c:
        yield c
