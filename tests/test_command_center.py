from __future__ import annotations

import json
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from unittest.mock import patch

from ai_growth_engineering.command_center import build_server
from ai_growth_engineering.storage import connect


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
            self.assertIn("Today’s 10 best buyers", html)
            self.assertIn("Scan public hiring source", html)
            self.assertIn("Record researched identity", html)
            self.assertIn("no-store", response.headers["Cache-Control"])
            self.assertEqual(response.headers["X-Frame-Options"], "DENY")
        with urllib.request.urlopen(self.base + "/api/state") as response:
            state = json.load(response)
        self.assertEqual(state["authority"]["mode"], "HUMAN_GATED")
        with urllib.request.urlopen(self.base + "/api/workbench") as response:
            workbench = json.load(response)
        self.assertEqual(workbench["drafts"], [])
        with urllib.request.urlopen(self.base + "/api/intelligence") as response:
            intelligence = json.load(response)
        self.assertEqual(intelligence["ranked_buyers"], [])
        with urllib.request.urlopen(self.base + "/revenue-intelligence") as response:
            revenue_html = response.read().decode()
        self.assertIn("Revenue Intelligence", revenue_html)

    def test_revenue_workspace_reads_only_the_intelligence_surfaces(self):
        with urllib.request.urlopen(self.base + "/revenue-intelligence") as response:
            html = response.read().decode()
        self.assertIn("/api/state", html)
        self.assertIn("/api/intelligence", html)
        self.assertIn("/api/signals/sources", html)
        # the eligibility checklist and the signal filters are on the page
        for surface in ('id="signal-ledger"', 'id="f-type"', 'id="f-conf"', 'id="f-age"',
                        'id="f-company"', 'id="f-text"', "gate-list", "Eligibility"):
            self.assertIn(surface, html)
        # unobserved prospects are summarised, not rendered as sixty identical rows
        self.assertIn("No observed intent event", html)
        self.assertIn("not yet looked at", html)
        for surface in ('id="dossier"', 'role="dialog"', "Signal history", 'id="held-ledger"', 'id="source-ledger"'):
            self.assertIn(surface, html)
        # scanning a public page is a read; contacting a person is not, and none of
        # the routes that reach a prospect may be callable from this screen.
        for reaching in ("/api/outbound/drafts", "/api/identities", "/record-send", "/record-reply", "/approve"):
            self.assertNotIn(reaching, html)
        for remote in ('src="http', 'href="http', "googleapis", "cdn."):
            self.assertNotIn(remote, html)

    def test_a_blocked_prospect_never_reaches_the_actionable_queue(self):
        with connect(self.db) as con:
            con.execute(
                """INSERT INTO prospects(
                     company, website, priority, target_roles, evidence, source_url, status
                   ) VALUES ('Blocked Ltd', 'https://blocked.example', 'A', 'Founder',
                             'Public B2B offer', 'https://blocked.example/about', 'disqualified')"""
            )
        self.post(
            "/api/signals",
            {
                "prospect_id": 1,
                "signal_type": "hiring",
                "source_url": "https://blocked.example/careers",
                "observed_fact": "The company published a revenue operations vacancy.",
                "commercial_interpretation": "The vacancy may indicate investment in pipeline operations.",
                "observed_at": "2026-08-29",
                "confidence": 0.95,
                "strength": 5,
                "freshness_half_life_days": 14,
            },
            expected=201,
        )
        self.post(
            "/api/identities",
            {
                "prospect_id": 1,
                "identity_type": "linkedin",
                "value": "https://www.linkedin.com/in/blocked-buyer",
                "provider": "operator_research",
                "verification_status": "verified",
                "source_url": "https://blocked.example/team",
                "observed_at": "2026-08-29",
                "confidence": 0.9,
            },
            expected=201,
        )
        with urllib.request.urlopen(self.base + "/api/intelligence") as response:
            state = json.load(response)
        self.assertEqual(state["eligible_count"], 0)
        self.assertEqual(state["ranked_buyers"], [])
        self.assertEqual(len(state["ineligible"]), 1)
        blocked = state["ineligible"][0]
        self.assertEqual(blocked["company"], "Blocked Ltd")
        self.assertEqual(blocked["signal_count"], 1)
        self.assertIn("Prospect status is disqualified", blocked["reasons"])

    def test_each_workspace_links_to_the_other_and_says_which_one_you_are_in(self):
        """Getting lost was the reported failure: a link that leaves the app looked
        exactly like one that scrolls the page, and the two used different names."""
        pages = {}
        for route in ("/", "/revenue-intelligence"):
            with urllib.request.urlopen(self.base + route) as response:
                pages[route] = response.read().decode()

        for route, html in pages.items():
            with self.subTest(route=route):
                # a labelled workspace group, separate from the in-page anchors
                self.assertIn("nav-app", html)
                self.assertIn(">Workspace<", html)
                self.assertIn(">On this page<", html)
                # both destinations reachable from either page, under one shared name
                self.assertIn('href="/revenue-intelligence"', html)
                self.assertIn('href="/"', html)
                self.assertIn("Revenue intelligence", html)
                self.assertIn("Command center", html)
                self.assertNotIn("Revenue ledger", html)
                # exactly one workspace marked as the one you are in
                self.assertEqual(html.count('aria-current="page"'), 1, html.count('aria-current'))

    def test_the_revenue_workspace_names_the_next_move(self):
        with urllib.request.urlopen(self.base + "/revenue-intelligence") as response:
            html = response.read().decode()
        self.assertIn('id="next"', html)
        self.assertIn("Do next", html)

    def test_a_taken_port_explains_itself_instead_of_a_traceback(self):
        """The bare failure is forty lines of socketserver internals ending in
        'Address already in use', which hides the likeliest cause: it is already open."""
        import argparse

        from ai_growth_engineering.cli import cmd_command_center

        args = argparse.Namespace(
            db=self.db, host="127.0.0.1", port=self.server.server_port, open_browser=False
        )
        with self.assertRaises(SystemExit) as raised:
            cmd_command_center(args)
        self.assertIn("already running", str(raised.exception))
        self.assertIn(f"127.0.0.1:{self.server.server_port}", str(raised.exception))

    def test_a_port_taken_by_something_else_says_so_and_offers_another(self):
        import argparse
        import socket

        from ai_growth_engineering.cli import cmd_command_center

        stranger = socket.socket()
        stranger.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        stranger.bind(("127.0.0.1", 0))
        stranger.listen(1)
        self.addCleanup(stranger.close)
        port = stranger.getsockname()[1]

        args = argparse.Namespace(db=self.db, host="127.0.0.1", port=port, open_browser=False)
        with self.assertRaises(SystemExit) as raised:
            cmd_command_center(args)
        message = str(raised.exception)
        self.assertIn("taken by something else", message)
        self.assertIn(f"--port {port + 1}", message)
        self.assertNotIn("already running", message)

    def test_another_http_server_on_the_port_is_not_mistaken_for_this_one(self):
        """A bare socket never answers /healthz, so it exercises the timeout path only.
        Distinguishing 'already running' from 'something else' needs a server that
        replies — with a body that is not ours."""
        import argparse
        import http.server
        import threading

        from ai_growth_engineering.cli import cmd_command_center

        class Impostor(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b'{"status":"ok","mode":"something_else"}')

            def log_message(self, *args):
                pass

        impostor = http.server.HTTPServer(("127.0.0.1", 0), Impostor)
        threading.Thread(target=impostor.serve_forever, daemon=True).start()
        self.addCleanup(impostor.shutdown)
        self.addCleanup(impostor.server_close)
        port = impostor.server_address[1]

        args = argparse.Namespace(db=self.db, host="127.0.0.1", port=port, open_browser=False)
        with self.assertRaises(SystemExit) as raised:
            cmd_command_center(args)
        message = str(raised.exception)
        self.assertIn("taken by something else", message)
        self.assertNotIn("already running", message)

    def test_write_routes_are_refused(self):
        request = urllib.request.Request(self.base + "/api/state", method="POST", data=b"{}")
        with self.assertRaises(urllib.error.HTTPError) as error:
            urllib.request.urlopen(request)
        self.assertEqual(error.exception.code, 405)
        self.assertEqual(error.exception.headers["Allow"], "GET")
        error.exception.close()

    def test_mutation_requires_an_explicit_intent_header(self):
        request = urllib.request.Request(
            self.base + "/api/outbound/drafts",
            method="POST",
            data=b"{}",
            headers={"Content-Type": "application/json"},
        )
        with self.assertRaises(urllib.error.HTTPError) as error:
            urllib.request.urlopen(request)
        self.assertEqual(error.exception.code, 403)
        error.exception.close()

    def test_outbound_workflow_runs_through_the_http_surface(self):
        with connect(self.db) as con:
            con.execute(
                """INSERT INTO prospects(
                     company, website, priority, target_roles, evidence, source_url, status
                   ) VALUES ('Acme', 'https://example.com', 'A', 'Founder', 'B2B service provider',
                             'https://example.com', 'qualified')"""
            )
        payload = {
            "prospect_id": 1,
            "recipient_identity": "founder@example.com",
            "recipient_class": "named_buyer",
            "channel": "email",
            "observation": "Your managed-security pages route assessment demand into the general enquiry form.",
            "economic_hypothesis": "That shared path may suppress qualified conversations rather than traffic being the constraint.",
            "cta": "Want me to send the one-page experiment map?",
            "metric": "qualified_conversation_rate",
            "source_url": "https://example.com/security",
        }
        created = self.post("/api/outbound/drafts", payload, expected=201)
        draft_id = created["draft"]["id"]
        self.assertEqual(created["draft"]["status"], "pending_approval")
        approved = self.post(f"/api/outbound/drafts/{draft_id}/approve", {})
        self.assertEqual(approved["draft"]["status"], "approved")
        sent = self.post(f"/api/outbound/drafts/{draft_id}/record-send", {})
        self.assertEqual(sent["draft"]["status"], "sent")
        replied = self.post(f"/api/outbound/drafts/{draft_id}/record-reply", {})
        self.assertEqual(replied["draft"]["status"], "replied")
        with urllib.request.urlopen(self.base + "/api/state") as response:
            state = json.load(response)
        metrics = {row["key"]: row["value"] for row in state["scoreboard"]}
        self.assertEqual(metrics["outreach_sent"], 1)
        self.assertEqual(metrics["meaningful_responses"], 1)

    def test_signal_and_identity_intake_feed_the_ranked_buyer_surface(self):
        with connect(self.db) as con:
            con.execute(
                """INSERT INTO prospects(
                     company, website, priority, target_roles, evidence, source_url, status
                   ) VALUES ('Acme', 'https://example.com', 'A', 'Founder', 'Public B2B offer',
                             'https://example.com/about', 'qualified')"""
            )
        created = self.post(
            "/api/signals",
            {
                "prospect_id": 1,
                "signal_type": "hiring",
                "source_url": "https://example.com/careers",
                "observed_fact": "The company published a revenue operations vacancy on its careers page.",
                "commercial_interpretation": "The vacancy may indicate current investment in pipeline operations and measurement.",
                "observed_at": "2026-08-29",
                "confidence": 0.9,
                "strength": 4,
                "freshness_half_life_days": 14,
            },
            expected=201,
        )
        signal_id = created["signal"]["signal_id"]
        saved = self.post(
            "/api/identities",
            {
                "prospect_id": 1,
                "identity_type": "linkedin",
                "value": "https://www.linkedin.com/in/example-buyer",
                "provider": "operator_research",
                "verification_status": "observed_published",
                "source_url": "https://example.com/team",
                "observed_at": "2026-08-29",
                "confidence": 0.8,
            },
            expected=201,
        )
        self.assertEqual(saved["identity"]["identity_type"], "linkedin")
        with urllib.request.urlopen(self.base + "/api/intelligence") as response:
            state = json.load(response)
        buyer = state["ranked_buyers"][0]
        self.assertEqual(buyer["signal"]["signal_id"], signal_id)
        self.assertEqual(buyer["recommended_channel"], "linkedin")
        self.assertEqual(buyer["recommended_action"], "prepare_approval_draft")

    def test_enrichment_route_rejects_private_network_targets(self):
        request = urllib.request.Request(
            self.base + "/api/enrichment/inspect",
            method="POST",
            data=json.dumps({"source_url": "http://127.0.0.1/"}).encode(),
            headers={
                "Content-Type": "application/json",
                "X-Command-Center-Intent": "mutate",
            },
        )
        with self.assertRaises(urllib.error.HTTPError) as error:
            urllib.request.urlopen(request)
        self.assertEqual(error.exception.code, 422)
        self.assertEqual(json.load(error.exception)["error"], "unsafe_source")
        error.exception.close()

    def test_hiring_scan_previews_without_persisting(self):
        with connect(self.db) as con:
            con.execute(
                """INSERT INTO prospects(
                     company, website, priority, target_roles, evidence, source_url, status
                   ) VALUES ('Acme', 'https://example.com', 'A', 'Revenue leader',
                             'Public B2B offer', 'https://example.com/about', 'qualified')"""
            )
        with patch(
            "ai_growth_engineering.hiring_signal_connector.PublicHiringSignalConnector.scan",
            return_value=[],
        ):
            result = self.post(
                "/api/signals/hiring/scan",
                {
                    "prospect_id": 1,
                    "source_url": "https://example.com/careers",
                    "max_age_days": 45,
                },
            )
        self.assertFalse(result["persisted"])
        self.assertEqual(result["candidates"], [])
        with connect(self.db) as con:
            self.assertEqual(con.execute("SELECT COUNT(*) FROM intent_signals").fetchone()[0], 0)

    def post(self, path: str, payload: dict, *, expected: int = 200) -> dict:
        request = urllib.request.Request(
            self.base + path,
            method="POST",
            data=json.dumps(payload).encode(),
            headers={
                "Content-Type": "application/json",
                "X-Command-Center-Intent": "mutate",
            },
        )
        with urllib.request.urlopen(request) as response:
            self.assertEqual(response.status, expected)
            return json.load(response)

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
