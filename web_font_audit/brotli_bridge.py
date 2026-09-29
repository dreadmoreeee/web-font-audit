"""Brotli decompression without the brotli package.

WOFF2 fonts are brotli-compressed. When the `brotli` module is not installed,
the compressed stream is served from a loopback-only HTTP server with
`Content-Encoding: br` and read back through Playwright's request client,
which decodes it. Nothing leaves the machine.
"""

from __future__ import annotations

import http.server
import itertools
import threading


class _Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802
        data = self.server.blobs.pop(self.path, None)
        if data is None:
            self.send_response(404)
            self.end_headers()
            return
        self.send_response(200)
        self.send_header("Content-Type", "application/octet-stream")
        self.send_header("Content-Encoding", "br")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *args):
        pass


class BrotliBridge:
    def __init__(self, playwright):
        self._server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
        self._server.blobs = {}
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()
        self._request = playwright.request.new_context()
        self._ids = itertools.count(1)

    def decompress(self, data: bytes) -> bytes:
        path = f"/blob/{next(self._ids)}"
        self._server.blobs[path] = data
        port = self._server.server_address[1]
        response = self._request.get(f"http://127.0.0.1:{port}{path}")
        if response.status != 200:
            raise ValueError("brotli bridge failed")
        return response.body()

    def close(self):
        try:
            self._request.dispose()
        finally:
            self._server.shutdown()
            self._server.server_close()
