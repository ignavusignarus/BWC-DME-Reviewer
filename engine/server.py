"""BWC Clipper local HTTP server.

Stdlib http.server only — no Flask/FastAPI. The handler dispatches GET and
POST requests to small route tables. Each handler returns a tuple
(status_code, body_dict). Future milestones extend the route tables.
"""

import json
import logging
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from typing import Callable

from engine.project import open_project
from engine.version import get_version

logger = logging.getLogger("bwc-clipper.server")


class BWCRequestHandler(BaseHTTPRequestHandler):
    """Routes requests to handler methods. JSON in, JSON out."""

    def log_message(self, format, *args):
        logger.debug("%s - %s", self.address_string(), format % args)

    def _get_routes(self) -> dict[str, Callable[[], tuple[int, dict]]]:
        return {
            "/api/health": self._handle_health,
            "/api/version": self._handle_version,
        }

    def _post_routes(self) -> dict[str, Callable[[dict], tuple[int, dict]]]:
        return {
            "/api/project/open": self._handle_project_open,
        }

    def do_GET(self):
        handler = self._get_routes().get(self.path)
        if handler is None:
            self._send_json(404, {"error": "not found", "path": self.path})
            return
        try:
            status, body = handler()
            self._send_json(status, body)
        except Exception as exc:  # pragma: no cover - defensive
            logger.exception("GET handler crashed for %s", self.path)
            self._send_json(500, {"error": "internal", "detail": str(exc)})

    def do_POST(self):
        handler = self._post_routes().get(self.path)
        if handler is None:
            self._send_json(404, {"error": "not found", "path": self.path})
            return
        body = self._read_json_body()
        if body is None:
            return  # error already sent by _read_json_body
        try:
            status, response_body = handler(body)
            self._send_json(status, response_body)
        except Exception as exc:  # pragma: no cover - defensive
            logger.exception("POST handler crashed for %s", self.path)
            self._send_json(500, {"error": "internal", "detail": str(exc)})

    def _read_json_body(self) -> dict | None:
        """Read and parse the request body as JSON. Sends 400 on failure and
        returns None; otherwise returns the parsed dict.
        """
        length_header = self.headers.get("Content-Length")
        if not length_header:
            self._send_json(400, {"error": "missing Content-Length / empty body"})
            return None
        try:
            content_length = int(length_header)
        except ValueError:
            self._send_json(400, {"error": "invalid Content-Length"})
            return None
        if content_length <= 0:
            self._send_json(400, {"error": "empty body"})
            return None
        raw = self.rfile.read(content_length)
        try:
            data = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            self._send_json(400, {"error": "malformed JSON", "detail": str(exc)})
            return None
        if not isinstance(data, dict):
            self._send_json(400, {"error": "body must be a JSON object"})
            return None
        return data

    # ── GET handlers ──

    def _handle_health(self) -> tuple[int, dict]:
        return 200, {"status": "ok"}

    def _handle_version(self) -> tuple[int, dict]:
        return 200, {"version": get_version()}

    # ── POST handlers ──

    def _handle_project_open(self, body: dict) -> tuple[int, dict]:
        path_str = body.get("path")
        if not isinstance(path_str, str) or not path_str:
            return 400, {"error": "missing 'path' field"}
        try:
            manifest = open_project(Path(path_str))
        except FileNotFoundError:
            return 404, {"error": "folder not found", "path": path_str}
        except NotADirectoryError:
            return 400, {"error": "path is not a directory", "path": path_str}
        return 200, manifest

    # ── Response helper ──

    def _send_json(self, status: int, body: dict):
        payload = json.dumps(body).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(payload)
