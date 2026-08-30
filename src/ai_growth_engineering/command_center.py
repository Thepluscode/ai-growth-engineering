"""Local, human-gated HTTP surface for the internal GrowthOps Command Center."""
from __future__ import annotations

import json
import re
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib.resources import files
from urllib.parse import urlparse

from .growthops import command_center_state
from .hiring_signal_connector import (
    add_hiring_source,
    list_hiring_sources,
    pending_hiring_candidates,
    preview_hiring_signals,
    scan_saved_hiring_sources,
)
from .outbound_workbench import (
    WorkbenchError,
    approve_draft,
    create_draft,
    record_manual_send,
    record_meaningful_reply,
    reject_draft,
    workbench_state,
)
from .signal_intelligence import (
    IntelligenceError,
    PublicPageEnrichmentProvider,
    add_identity,
    add_intent_signal,
    intelligence_state,
)
from .storage import init_db


MAX_JSON_BYTES = 64 * 1024
_DRAFT_ACTION = re.compile(
    r"^/api/outbound/drafts/(?P<draft_id>\d+)/(?P<action>approve|reject|record-send|record-reply)$"
)


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
            if path == "/revenue-intelligence":
                self._send(200, _asset("revenue_intelligence.html"), "text/html; charset=utf-8")
                return
            if path == "/api/state":
                payload = json.dumps(command_center_state(db_path), separators=(",", ":")).encode()
                self._send(200, payload, "application/json; charset=utf-8")
                return
            if path == "/api/workbench":
                self._send_json(200, workbench_state(db_path))
                return
            if path == "/api/intelligence":
                self._send_json(200, intelligence_state(db_path))
                return
            if path == "/api/signals/sources":
                self._send_json(200, {
                    "sources": list_hiring_sources(db_path),
                    "pending": pending_hiring_candidates(db_path),
                })
                return
            if path == "/healthz":
                self._send(200, b'{"status":"ok","mode":"human_gated"}', "application/json")
                return
            self._send(404, b'{"error":"not_found"}', "application/json")

        def do_POST(self) -> None:  # noqa: N802
            path = urlparse(self.path).path
            if path in {"/api/state", "/api/workbench", "/api/intelligence"}:
                self._send_json(405, {"error": "method_not_allowed"}, allow="GET")
                return
            match = _DRAFT_ACTION.match(path)
            mutation_routes = {
                "/api/outbound/drafts",
                "/api/signals",
                "/api/signals/hiring/scan",
                "/api/signals/sources",
                "/api/signals/sources/scan",
                "/api/identities",
                "/api/enrichment/inspect",
            }
            if path not in mutation_routes and match is None:
                self._send_json(404, {"error": "not_found"})
                return
            if self.headers.get("X-Command-Center-Intent") != "mutate":
                self._send_json(403, {"error": "explicit_intent_required"})
                return
            try:
                payload = self._read_json()
                if path == "/api/outbound/drafts":
                    self._send_json(201, {"draft": create_draft(db_path, payload)})
                    return
                if path == "/api/signals":
                    self._send_json(201, {"signal": add_intent_signal(db_path, payload)})
                    return
                if path == "/api/signals/hiring/scan":
                    self._send_json(200, preview_hiring_signals(db_path, payload))
                    return
                if path == "/api/signals/sources":
                    self._send_json(201, {"source": add_hiring_source(db_path, payload)})
                    return
                if path == "/api/signals/sources/scan":
                    self._send_json(200, scan_saved_hiring_sources(db_path))
                    return
                if path == "/api/identities":
                    self._send_json(201, {"identity": add_identity(db_path, payload)})
                    return
                if path == "/api/enrichment/inspect":
                    source_url = str(payload.get("source_url") or "").strip()
                    candidates = PublicPageEnrichmentProvider().inspect(source_url)
                    self._send_json(
                        200,
                        {
                            "source_url": source_url,
                            "provider": "public_page",
                            "persisted": False,
                            "candidates": [value.as_dict() for value in candidates],
                        },
                    )
                    return
                draft_id = int(match.group("draft_id"))
                action = match.group("action")
                handlers = {
                    "approve": approve_draft,
                    "reject": reject_draft,
                    "record-send": record_manual_send,
                    "record-reply": record_meaningful_reply,
                }
                self._send_json(200, {"draft": handlers[action](db_path, draft_id)})
            except WorkbenchError as exc:
                status = 404 if exc.code.endswith("not_found") else 409 if exc.code in {
                    "suppressed", "active_draft_exists", "approval_required",
                    "send_required", "invalid_transition",
                } else 422
                self._send_json(status, {"error": exc.code, "message": str(exc)})
            except IntelligenceError as exc:
                status = 404 if exc.code.endswith("not_found") else 422
                self._send_json(status, {"error": exc.code, "message": str(exc)})
            except (json.JSONDecodeError, UnicodeDecodeError):
                self._send_json(400, {"error": "invalid_json"})
            except ValueError as exc:
                self._send_json(422, {"error": "invalid_field", "message": str(exc)})

        def _read_json(self) -> dict[str, object]:
            content_type = self.headers.get("Content-Type", "").split(";", 1)[0].strip()
            if content_type != "application/json":
                raise WorkbenchError("json_required", "Content-Type must be application/json")
            try:
                length = int(self.headers.get("Content-Length", "0"))
            except ValueError as exc:
                raise WorkbenchError("invalid_field", "Invalid Content-Length") from exc
            if length <= 0 or length > MAX_JSON_BYTES:
                raise WorkbenchError("invalid_field", "JSON body must be between 1 byte and 64 KiB")
            value = json.loads(self.rfile.read(length).decode("utf-8"))
            if not isinstance(value, dict):
                raise WorkbenchError("invalid_field", "JSON body must be an object")
            return value

        def _send_json(
            self, status: int, value: dict[str, object], *, allow: str | None = None
        ) -> None:
            self._send(
                status,
                json.dumps(value, separators=(",", ":")).encode(),
                "application/json; charset=utf-8",
                allow=allow,
            )

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
    print(f"Revenue Intelligence: {url}/revenue-intelligence")
    print("Mode: INTERNAL / HUMAN GATED / NO AUTOSEND")
    if open_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
