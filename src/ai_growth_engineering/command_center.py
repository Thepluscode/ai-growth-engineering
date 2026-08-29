"""Local, read-only HTTP surface for the internal GrowthOps Command Center."""
from __future__ import annotations

import json
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib.resources import files
from urllib.parse import urlparse

from .growthops import command_center_state
from .storage import init_db


def _asset(name: str) -> bytes:
    return files("ai_growth_engineering").joinpath("static", name).read_bytes()


def build_server(
    db_path: str, host: str = "127.0.0.1", port: int = 8787
) -> ThreadingHTTPServer:
    if host not in {"127.0.0.1", "localhost", "::1"}:
        raise ValueError("Command Center may bind only to a loopback host")
    init_db(db_path)

    class CommandCenterHandler(BaseHTTPRequestHandler):
        server_version = "AGECommandCenter/0.1"

        def do_GET(self) -> None:  # noqa: N802
            path = urlparse(self.path).path
            if path == "/":
                self._send(200, _asset("command_center.html"), "text/html; charset=utf-8")
                return
            if path == "/api/state":
                payload = json.dumps(command_center_state(db_path), separators=(",", ":")).encode()
                self._send(200, payload, "application/json; charset=utf-8")
                return
            if path == "/healthz":
                self._send(200, b'{"status":"ok","mode":"read_only"}', "application/json")
                return
            self._send(404, b'{"error":"not_found"}', "application/json")

        def do_POST(self) -> None:  # noqa: N802
            self._send(405, b'{"error":"read_only"}', "application/json", allow="GET")

        def _send(
            self, status: int, body: bytes, content_type: str, *, allow: str | None = None
        ) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Security-Policy", "default-src 'self'; style-src 'unsafe-inline'; script-src 'unsafe-inline'; connect-src 'self'; img-src 'self' data:")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("X-Frame-Options", "DENY")
            if allow:
                self.send_header("Allow", allow)
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format: str, *args: object) -> None:
            return

    return ThreadingHTTPServer((host, port), CommandCenterHandler)


def serve_command_center(
    db_path: str, *, host: str = "127.0.0.1", port: int = 8787, open_browser: bool = False
) -> None:
    server = build_server(db_path, host, port)
    url = f"http://{host}:{server.server_port}"
    print(f"GrowthOps Command Center: {url}")
    print("Mode: INTERNAL / READ ONLY / PROPOSE ONLY")
    if open_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
