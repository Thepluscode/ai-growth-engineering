"""Qualified is not send-ready. A market-experiment message is recorded only through a verified
direct route, a connection request is access and never a send, and delivery needs evidence."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from ai_growth_engineering import registries
from ai_growth_engineering.demand_funnel import report
from ai_growth_engineering.outbound_workbench import (
    DIRECT_VERIFIED, PROFILE_VERIFIED, ROUTE_UNVERIFIED, WorkbenchError, approve_draft, create_draft,
    get_draft, hold_draft, record_connection_accepted, record_connection_request, record_delivery,
    record_manual_send, reject_draft, route_status, workbench_state)
from ai_growth_engineering.storage import connect, init_db

T1, T2, T3 = "2026-10-06T09:00:00+00:00", "2026-10-07T09:00:00+00:00", "2026-10-08T09:00:00+00:00"
PROFILE = "https://www.linkedin.com/in/example-buyer"


TEAM = "https://example.com/team"
PAGES = {TEAM: "<p>Contact: <a href='mailto:buyer@example.com'>buyer@example.com</a></p>",
         "https://example.com/unrelated": "<p>No addresses here.</p>"}


class RouteGate(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.db = str(Path(self.tmp.name) / "g.db")
        patcher = mock.patch("ai_growth_engineering.marketer.fetch_page", lambda url: PAGES.get(url, ""))
        patcher.start()
        self.addCleanup(patcher.stop)
        init_db(self.db)
        with connect(self.db) as con:
            for pid in (1, 2, 3):
                con.execute("""INSERT INTO prospects(id, company, status) VALUES (?, ?, 'researched_verified')""",
                            (pid, f"Co{pid}"))
        registries.add(self.db, "markets", {"market_id": "MKT-S", "hypothesis": "h", "status": "active"})
        registries.add(self.db, "market_experiments", {
            "link_id": "L", "market_id": "MKT-S", "experiment_id": "EXP-S", "layer": "DEMAND",
            "protocol": "discovery-v1", "exposure_event": "message_sent", "positive_event": "reply_meaningful"})

    def draft(self, identity, pid=1, channel="linkedin", route=None, **extra):
        return create_draft(self.db, {**extra,
            "prospect_id": pid, "recipient_identity": identity, "recipient_class": "named_buyer",
            "channel": channel, "experiment_id": extra.get("experiment_id", "EXP-S"),
            "observation": "Your managed SOC page says signals are spread across several systems.",
            "economic_hypothesis": "I am trying to understand how teams like yours reconstruct an incident.",
            "cta": "When did this last happen?", "metric": "qualified conversations",
            "source_url": "https://example.com/soc"}, route_source_url=route or "")

    def test_a_name_to_look_up_later_is_not_a_route(self):
        d = self.draft("Jo Bloggs at Co1 (find on LinkedIn by name)")
        approve_draft(self.db, d["id"])
        self.assertEqual(route_status(self.db, get_draft(self.db, d["id"])), ROUTE_UNVERIFIED)
        for attempt in (lambda: record_manual_send(self.db, d["id"], T1),
                        lambda: record_connection_request(self.db, d["id"], T1)):
            with self.assertRaises(WorkbenchError):
                attempt()
        self.assertEqual(get_draft(self.db, d["id"])["status"], "approved")

    def test_profile_route_connects_first_and_delivers_only_after_acceptance(self):
        d = self.draft(PROFILE)
        with self.assertRaises(WorkbenchError) as ctx:
            record_connection_request(self.db, d["id"], T1)
        self.assertEqual(ctx.exception.code, "approval_required")
        approve_draft(self.db, d["id"])
        self.assertEqual(route_status(self.db, get_draft(self.db, d["id"])), PROFILE_VERIFIED)
        with self.assertRaises(WorkbenchError) as ctx:
            record_manual_send(self.db, d["id"], T1)
        self.assertEqual(ctx.exception.code, "route_unverified")
        with self.assertRaises(WorkbenchError) as ctx:
            record_connection_accepted(self.db, d["id"], T2)
        self.assertEqual(ctx.exception.code, "request_required")

        record_connection_request(self.db, d["id"], T1)
        m = report(self.db)["markets"][0]
        self.assertEqual((m["connection_requests_sent"], m["messages_attempted"], m["delivered_to_named_buyers"]),
                         (1, 0, 0), "a connection request is access, never a send")

        self.assertEqual(report(self.db)["markets"][0]["connections_pending"], 1)
        record_connection_accepted(self.db, d["id"], T2)
        self.assertEqual(route_status(self.db, get_draft(self.db, d["id"])), DIRECT_VERIFIED)
        record_manual_send(self.db, d["id"], T3)
        m = report(self.db)["markets"][0]
        self.assertEqual((m["connections_accepted"], m["connections_pending"], m["messages_attempted"],
                          m["delivered_to_named_buyers"], m["attempted_delivery_unverified"]), (1, 0, 1, 0, 1),
                         "a send, even to an accepted connection, never manufactures its own delivery")
        record_delivery(self.db, d["id"], "2026-10-09T09:00:00+00:00", "linkedin_seen_indicator")
        m = report(self.db)["markets"][0]
        self.assertEqual((m["delivered_to_named_buyers"], m["attempted_delivery_unverified"]), (1, 0))

    def test_a_guessed_email_is_not_a_route_and_cannot_be_sent(self):
        """Found 2026-10-13 (Codex review): any well-formed address read as DIRECT_VERIFIED, so a
        guessed first.last@company address could enter the experiment send path."""
        d = self.draft("first.last@example.com", channel="email")
        approve_draft(self.db, d["id"])
        self.assertEqual(route_status(self.db, get_draft(self.db, d["id"])), ROUTE_UNVERIFIED)
        with self.assertRaises(WorkbenchError) as ctx:
            record_manual_send(self.db, d["id"], T1)
        self.assertEqual(ctx.exception.code, "route_unverified")
        # A plausible URL in the request body is not verification: the API passes its body here.
        forged = self.draft("guess@example.com", pid=2, channel="email",
                            route_evidence_url="https://example.com/unrelated",
                            route_verified_at="2026-10-13T00:00:00+00:00", route_verification="trust me")
        self.assertEqual(route_status(self.db, get_draft(self.db, forged["id"])), ROUTE_UNVERIFIED)

    def test_fabricated_verification_metadata_is_not_accepted_from_any_caller(self):
        """Founder review of PR #4: an internal caller could pass a made-up URL, time and method
        and the stored fields alone made the guess DIRECT_VERIFIED. Only a fetched page vouches now."""
        forged = {"url": TEAM, "verified_at": "2026-10-13T00:00:00+00:00", "method": "trust me"}
        with self.assertRaises(TypeError):
            create_draft(self.db, {"prospect_id": 1, "recipient_identity": "guess@example.com"},
                         route_verification=forged)
        for page in ("https://example.com/unrelated", "https://example.com/missing", TEAM):
            with self.subTest(page=page), self.assertRaises(WorkbenchError) as ctx:
                self.draft("guess@example.com", channel="email", route=page)
            self.assertEqual(ctx.exception.code, "route_not_on_page")
        self.assertEqual(workbench_state(self.db)["total_drafts"], 0)

    def test_route_evidence_in_any_other_format_is_not_a_route(self):
        """Codex review of PR #4: a row written before the fetch moved into create_draft keeps its
        fields; only evidence in the format the fetching path writes counts."""
        d = self.draft("buyer@example.com", channel="email", route=TEAM)
        self.assertEqual(route_status(self.db, get_draft(self.db, d["id"])), DIRECT_VERIFIED)
        with connect(self.db) as con:
            con.execute("UPDATE outbound_drafts SET route_verification = 'trust me' WHERE id = ?", (d["id"],))
        self.assertEqual(route_status(self.db, get_draft(self.db, d["id"])), ROUTE_UNVERIFIED)

    def test_an_unpublished_email_cannot_be_recorded_as_sent_even_outside_an_experiment(self):
        """Codex review of PR #4: the send gate applied only to experiment drafts."""
        guess = self.draft("guess@example.com", channel="email", experiment_id="")
        published = self.draft("buyer@example.com", pid=2, channel="email", route=TEAM, experiment_id="")
        for d in (guess, published):
            approve_draft(self.db, d["id"])
        with self.assertRaises(WorkbenchError) as ctx:
            record_manual_send(self.db, guess["id"], T1)
        self.assertEqual(ctx.exception.code, "route_unverified")
        record_manual_send(self.db, published["id"], T1)
        self.assertEqual(get_draft(self.db, published["id"])["status"], "sent")

    def test_a_published_email_is_direct_but_delivery_still_needs_evidence(self):
        d = self.draft("buyer@example.com", channel="email", route=TEAM)
        self.assertEqual(route_status(self.db, get_draft(self.db, d["id"])), DIRECT_VERIFIED)
        self.assertEqual(get_draft(self.db, d["id"])["route_evidence_url"], TEAM)
        self.assertIn("sha256", get_draft(self.db, d["id"])["route_verification"])
        approve_draft(self.db, d["id"])
        record_manual_send(self.db, d["id"], T1)
        self.assertEqual(report(self.db)["markets"][0]["attempted_delivery_unverified"], 1)
        with self.assertRaises(WorkbenchError) as ctx:
            record_delivery(self.db, d["id"], T2, "we sent it")
        self.assertEqual(ctx.exception.code, "delivery_evidence_required")

    def test_held_and_rejected_drafts_leave_the_queue_with_their_reason(self):
        held, rejected = self.draft(PROFILE, pid=1), self.draft(PROFILE, pid=2)
        with self.assertRaises(WorkbenchError):
            hold_draft(self.db, held["id"], "")
        hold_draft(self.db, held["id"], "MARKET_PARKED")
        reject_draft(self.db, rejected["id"], "SUPERSEDED_COPY_AND_MISSING_EVIDENCE_TRIGGER")
        self.assertEqual((get_draft(self.db, held["id"])["status"], get_draft(self.db, held["id"])["status_reason"]),
                         ("held", "MARKET_PARKED"))
        self.assertEqual(get_draft(self.db, rejected["id"])["status_reason"],
                         "SUPERSEDED_COPY_AND_MISSING_EVIDENCE_TRIGGER")
        with self.assertRaises(WorkbenchError):
            approve_draft(self.db, held["id"])
        self.assertEqual(workbench_state(self.db)["counts"]["pending_approval"], 0)

    def test_an_approval_can_be_withdrawn_only_before_the_buyer_is_contacted(self):
        untouched, contacted = self.draft(PROFILE, pid=1), self.draft(PROFILE, pid=2)
        for d in (untouched, contacted):
            approve_draft(self.db, d["id"])
        hold_draft(self.db, untouched["id"], "ROLE_AND_BUYER_FIT_UNVERIFIED")
        self.assertEqual(get_draft(self.db, untouched["id"])["status"], "held")
        with self.assertRaises(WorkbenchError):
            record_connection_request(self.db, untouched["id"], T1)

        record_connection_request(self.db, contacted["id"], T1)
        with self.assertRaises(WorkbenchError) as ctx:
            hold_draft(self.db, contacted["id"], "ROLE_AND_BUYER_FIT_UNVERIFIED")
        self.assertEqual(ctx.exception.code, "already_contacted")
        self.assertEqual(get_draft(self.db, contacted["id"])["status"], "approved")


if __name__ == "__main__":
    unittest.main()
