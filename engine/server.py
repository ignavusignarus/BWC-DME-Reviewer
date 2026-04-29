"""BWC Clipper local HTTP server.

Stdlib http.server only — no Flask/FastAPI. The handler dispatches GET requests
to a small route table. Future milestones extend this with POST handlers and
WebSocket support; for Milestone 0 we serve only /api/health and /api/version.
"""

import json
import logging
from http.server import BaseHTTPRequestHandler

from engine.version import get_version

logger = logging.getLogger("bwc-clipper.server")


class BWCRequestHandler(BaseHTTPRequestHandler):
    """Routes GET requests to handler methods. JSON in, JSON out."""

    # Suppress default access logging — we use our own logger.
    def log_message(self, format, *args):
        logger.debug("%s - %s", self.address_string(), format % args)

    def do_GET(self):
        routes = {
            "/api/health": self._handle_health,
            "/api/version": self._handle_version,
        }
        handler = routes.get(self.path)
        if handler is None:
            self._send_json(404, {"error": "not found", "path": self.path})
            return
        try:
            handler()
        except Exception as exc:  # pragma: no cover - defensive
            logger.exception("handler crashed for %s", self.path)
            self._send_json(500, {"error": "internal", "detail": str(exc)})

    def _handle_health(self):
        self._send_json(200, {"status": "ok"})

    def _handle_version(self):
        self._send_json(200, {"version": get_version()})

    def _send_json(self, status: int, body: dict):
        payload = json.dumps(body).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        # Permissive CORS — only ever bound to 127.0.0.1, called from the
        # Electron renderer which loads from file:// or app://.
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(payload)
