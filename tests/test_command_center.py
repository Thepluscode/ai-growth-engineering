from __future__ import annotations

import json
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path

from ai_growth_engineering.command_center import build_server


class CommandCenterServerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.db = str(Path(self.tmp.name) / "growth.db")
        self.server = build_server(self.db, port=0)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)
        self.base = f"http://127.0.0.1:{self.server.server_port}"

    def test_interface_and_state_are_served_locally(self):
        with urllib.request.urlopen(self.base + "/") as response:
            html = response.read().decode()
            self.assertIn("GrowthOps", html)
            self.assertIn("Command Center", html)
            self.assertIn("no-store", response.headers["Cache-Control"])
            self.assertEqual(response.headers["X-Frame-Options"], "DENY")
        with urllib.request.urlopen(self.base + "/api/state") as response:
            state = json.load(response)
        self.assertEqual(state["authority"]["mode"], "PROPOSE_ONLY")

    def test_write_routes_are_refused(self):
        request = urllib.request.Request(self.base + "/api/state", method="POST", data=b"{}")
        with self.assertRaises(urllib.error.HTTPError) as error:
            urllib.request.urlopen(request)
        self.assertEqual(error.exception.code, 405)
        self.assertEqual(error.exception.headers["Allow"], "GET")
        error.exception.close()

    def test_unknown_route_is_not_found(self):
        with self.assertRaises(urllib.error.HTTPError) as error:
            urllib.request.urlopen(self.base + "/missing")
        self.assertEqual(error.exception.code, 404)
        error.exception.close()

    def test_non_loopback_bind_is_refused(self):
        with self.assertRaisesRegex(ValueError, "loopback"):
            build_server(self.db, host="0.0.0.0", port=0)


if __name__ == "__main__":
    unittest.main()
