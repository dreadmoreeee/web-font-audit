"""Load pages in headless Chromium and collect raw font data."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlsplit

from . import css as css_mod
from .brotli_bridge import BrotliBridge
from .fonts import brotli_module

DEFAULT_USER_AGENT = "web-font-audit/1.0 (+https://github.com/dreadmoreeee/web-font-audit)"
FONT_EXTENSIONS = (".woff2", ".woff", ".ttf", ".otf", ".eot")
PAGE_SCRIPT = (Path(__file__).with_name("page_script.js")).read_text(encoding="utf-8")


@dataclass
class FontResponse:
    url: str
    status: int
    content_type: str
    transfer_bytes: int
    decoded_bytes: int
    body: bytes
    requests: int = 1


@dataclass
class PageData:
    url: str
    final_url: str = ""
    status: int | None = None
    error: str = ""
    viewport: tuple[int, int] = (0, 0)
    fonts: list[FontResponse] = field(default_factory=list)
    faces: list[css_mod.FontFace] = field(default_factory=list)
    usage: list[dict] = field(default_factory=list)
    preloads: list[dict] = field(default_factory=list)
    document_fonts: list[dict] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


def _is_font_response(response) -> bool:
    if response.request.resource_type == "font":
        return True
    ctype = (response.headers.get("content-type") or "").lower()
    if ctype.startswith("font/") or "font-woff" in ctype or "x-font" in ctype:
        return True
    return urlsplit(response.url).path.lower().endswith(FONT_EXTENSIONS)


def _strip_fragment(url: str) -> str:
    return url.split("#", 1)[0]


class Collector:
    """One Chromium instance reused for several pages."""

    def __init__(self, user_agent: str = DEFAULT_USER_AGENT, viewport=(1366, 768),
                 timeout: float = 30.0, settle: float = 1.0):
        from playwright.sync_api import sync_playwright

        self.user_agent = user_agent
        self.viewport = viewport
        self.timeout_ms = int(timeout * 1000)
        self.settle = settle
        self._pw = sync_playwright().start()
        self._browser = self._pw.chromium.launch()
        self._bridge = None
        self.brotli = "module" if brotli_module() is not None else "browser"

    def decompress(self, data: bytes) -> bytes:
        if self._bridge is None:
            self._bridge = BrotliBridge(self._pw)
        return self._bridge.decompress(data)

    def close(self):
        if self._bridge is not None:
            self._bridge.close()
        self._browser.close()
        self._pw.stop()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    def collect(self, url: str) -> PageData:
        data = PageData(url=url)
        context = self._browser.new_context(
            user_agent=self.user_agent,
            viewport={"width": self.viewport[0], "height": self.viewport[1]},
            service_workers="block",
        )
        try:
            self._collect(context, url, data)
        finally:
            context.close()
        return data

    def _collect(self, context, url: str, data: PageData):
        page = context.new_page()
        font_responses = []
        css_responses = {}

        def on_response(response):
            if response.url.startswith("data:"):
                return
            if response.request.resource_type == "stylesheet":
                css_responses[_strip_fragment(response.url)] = response
            elif _is_font_response(response):
                font_responses.append(response)

        page.on("response", on_response)
        try:
            main = page.goto(url, wait_until="load", timeout=self.timeout_ms)
        except Exception as exc:  # network errors, timeouts
            data.error = str(exc).splitlines()[0]
            return
        data.status = main.status if main else None
        data.final_url = page.url
        try:
            page.wait_for_load_state("networkidle", timeout=min(self.timeout_ms, 10000))
        except Exception:
            data.notes.append("network did not go idle within 10 s; late fonts may be missing")
        try:
            page.evaluate("() => document.fonts ? document.fonts.ready.then(() => true) : true")
        except Exception:
            pass
        if self.settle:
            time.sleep(self.settle)

        raw = page.evaluate(PAGE_SCRIPT)
        data.viewport = tuple(raw["viewport"])
        data.usage = raw["usage"]
        data.preloads = raw["preloads"]
        data.document_fonts = raw["documentFonts"]
        data.faces = self._faces(context, raw["sheets"], css_responses, data)
        data.fonts = self._font_files(font_responses, data)

    def _faces(self, context, sheets, css_responses, data: PageData):
        faces: list[css_mod.FontFace] = []
        visited = set()

        def css_text(href):
            response = css_responses.get(_strip_fragment(href))
            try:
                if response is not None:
                    return response.text()
                fetched = context.request.get(href, timeout=self.timeout_ms)
                if fetched.ok:
                    return fetched.text()
            except Exception:
                pass
            data.notes.append(f"could not read stylesheet {href}")
            return ""

        def from_text(href, depth):
            if href in visited or depth > 4:
                return
            visited.add(href)
            text = css_text(href)
            for imported in css_mod.parse_imports(text, href):
                from_text(imported, depth + 1)
            faces.extend(css_mod.parse_font_faces(text, href))

        for sheet in sheets:
            if sheet["crossOrigin"]:
                if sheet["href"]:
                    from_text(sheet["href"], 0)
                continue
            if sheet["href"]:
                visited.add(sheet["href"])
            for text in sheet["faces"]:
                faces.extend(css_mod.parse_font_faces(text, sheet["base"]))
        for i, face in enumerate(faces):
            face.order = i
        return faces

    def _font_files(self, responses, data: PageData):
        by_url: dict[str, FontResponse] = {}
        for response in responses:
            url = _strip_fragment(response.url)
            if url in by_url:
                by_url[url].requests += 1
                continue
            try:
                body = response.body()
            except Exception:
                body = b""
            try:
                sizes = response.request.sizes()
                transfer = sizes.get("responseBodySize", 0) + sizes.get("responseHeadersSize", 0)
            except Exception:
                transfer = 0
            if transfer <= 0:
                transfer = len(body)
            by_url[url] = FontResponse(
                url=url,
                status=response.status,
                content_type=response.headers.get("content-type", ""),
                transfer_bytes=transfer,
                decoded_bytes=len(body),
                body=body,
            )
        return list(by_url.values())


def polite_sleep(last: float | None, delay: float) -> float:
    """Sleep so page loads are at least `delay` seconds apart; returns now."""
    if last is not None:
        wait = delay - (time.monotonic() - last)
        if wait > 0:
            time.sleep(wait)
    return time.monotonic()
