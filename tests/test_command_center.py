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
