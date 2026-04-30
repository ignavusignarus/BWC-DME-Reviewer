"""dev_server.py — combined static + reverse-proxy server for the Chrome harness.

Serves dev-chrome.html / dev-shim.js / editor-bundle.js (and any other repo-root
file) at /, and forwards /api/* (plus media routes that share /api prefix) to
the engine running on a separate loopback port.

Usage:
    python dev_server.py --engine-port 54959 [--listen-port 8765]

Why a proxy instead of `python -m http.server`?
  - Same-origin avoids CORS preflight for the JSON POST routes.
  - editor/components/reviewer/MediaPane.jsx uses *relative* URLs
    (`/api/source/audio?...`); they only work when served from the same origin
    that hosts /api. The proxy makes that work without touching renderer code.

Production (Electron) does NOT use this file — it spawns serve.py and loads
index.html via file://. This server exists solely so Claude can drive the UI
from a real Chrome instance for end-to-end QA.
"""
from __future__ import annotations

import argparse
import http.client
import logging
import sys
from http.server import HTTPServer, SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

REPO_ROOT = Path(__file__).resolve().parent
PROXY_PREFIXES = ("/api/",)
HOP_BY_HOP = {
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailers",
    "transfer-encoding",
    "upgrade",
}

logger = logging.getLogger("dev_server")


def make_handler(engine_host: str, engine_port: int):
    class Handler(SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=str(REPO_ROOT), **kwargs)

        def log_message(self, fmt, *args):  # quieter than default
            logger.info("%s - %s", self.address_string(), fmt % args)

        def _is_proxy(self):
            path = urlsplit(self.path).path
            return any(path.startswith(p) for p in PROXY_PREFIXES)

        def _proxy(self, method: str, body: bytes | None = None):
            conn = http.client.HTTPConnection(engine_host, engine_port, timeout=300)
            try:
                # Forward headers, drop hop-by-hop and Host (let conn set it).
                forwarded = {}
                for k, v in self.headers.items():
                    if k.lower() in HOP_BY_HOP or k.lower() == "host":
                        continue
                    forwarded[k] = v
                conn.request(method, self.path, body=body, headers=forwarded)
                resp = conn.getresponse()
                self.send_response(resp.status, resp.reason)
                for k, v in resp.getheaders():
                    if k.lower() in HOP_BY_HOP:
                        continue
                    self.send_header(k, v)
                self.end_headers()
                # Stream body in chunks.
                while True:
                    chunk = resp.read(65536)
                    if not chunk:
                        break
                    try:
                        self.wfile.write(chunk)
                    except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
                        return
            except Exception as exc:  # noqa: BLE001
                logger.exception("proxy %s %s failed", method, self.path)
                try:
                    self.send_response(502)
                    self.send_header("Content-Type", "text/plain")
                    self.end_headers()
                    self.wfile.write(f"upstream error: {exc}".encode("utf-8"))
                except Exception:
                    pass
            finally:
                try:
                    conn.close()
                except Exception:
                    pass

        def _read_body(self) -> bytes:
            length = int(self.headers.get("Content-Length", "0") or 0)
            return self.rfile.read(length) if length > 0 else b""

        def do_GET(self):  # noqa: N802
            if self._is_proxy():
                return self._proxy("GET")
            return super().do_GET()

        def do_HEAD(self):  # noqa: N802
            if self._is_proxy():
                return self._proxy("HEAD")
            return super().do_HEAD()

        def do_POST(self):  # noqa: N802
            if self._is_proxy():
                return self._proxy("POST", body=self._read_body())
            self.send_response(405)
            self.end_headers()

        def do_OPTIONS(self):  # noqa: N802
            # Same-origin in our setup means preflight is rare, but a few stacks
            # still send one. Reply with permissive headers.
            self.send_response(204)
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS, HEAD")
            self.send_header("Access-Control-Allow-Headers", "Content-Type, Range")
            self.end_headers()

    return Handler


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--engine-port", type=int, required=True)
    parser.add_argument("--engine-host", default="127.0.0.1")
    parser.add_argument("--listen-port", type=int, default=8765)
    parser.add_argument("--listen-host", default="127.0.0.1")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(message)s")

    handler_cls = make_handler(args.engine_host, args.engine_port)
    server = ThreadingHTTPServer((args.listen_host, args.listen_port), handler_cls)
    logger.info(
        "dev-server static=%s:%s -> proxy /api/* to %s:%s",
        args.listen_host, args.listen_port, args.engine_host, args.engine_port,
    )
    print(f"DEV_SERVER_READY port={args.listen_port} engine={args.engine_port}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
