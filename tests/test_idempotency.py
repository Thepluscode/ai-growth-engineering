"""A repeated source identity is a replay only when it repeats the same fact.

The event id is derived from (source, source_record_id, event_type), so a re-import lands on
the same row. That made every second arrival look like a harmless duplicate — including one
that said something different: a payment with another amount, a send on another date, a reply
moved to another experiment. The first version silently won and the disagreement vanished.

Same identity + same immutable payload  -> IDEMPOTENT_REPLAY
Same identity + different payload       -> IDEMPOTENCY_CONFLICT: refused, audited, original kept
"""
from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from ai_growth_engineering.adapters import StripeAdapter, ingest
from ai_growth_engineering.funnel_events import EventError, effective_events, record_event
from ai_growth_engineering.storage import connect, init_db


def send(**overrides) -> dict:
    values = {"event_type": "message_sent", "occurred_at": "2026-09-01", "company": "Acme Ltd",
              "person_id": "P-01", "channel": "email", "experiment_id": "EXP-ACQ-0009",
              "campaign_id": "CMP-1", "source": "gmail", "source_record_id": "msg-1",
              "provenance": "platform_export"}
    values.update(overrides)
    return values


def stripe_payment(amount: int, created: int = 1789473600, event_id: str = "evt_1") -> dict:
    return {"id": event_id, "object": "event", "type": "payment_intent.succeeded", "livemode": True,
            "created": created,
            "data": {"object": {"id": "pi_live_0001", "object": "payment_intent", "amount": amount,
                                "amount_received": amount, "currency": "gbp", "customer": "cus_1",
                                "metadata": {"company": "Acme Ltd"}}}}


class Case(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.db = str(Path(self.tmp.name) / "g.db")
        init_db(self.db)

    def rows(self, sql: str, *params):
        with connect(self.db) as con:
            return [dict(r) for r in con.execute(sql, params)]

    def conflicts(self):
        return self.rows("SELECT * FROM idempotency_conflicts ORDER BY id")


class IdenticalReplayIsIdempotent(Case):
    def test_the_same_fact_twice_is_one_event(self):
        first = record_event(self.db, send())
        again = record_event(self.db, send())
        self.assertTrue(first["inserted"])
        self.assertFalse(again["inserted"])
        self.assertEqual(again["status"], "IDEMPOTENT_REPLAY")
        self.assertEqual(len(effective_events(self.db)), 1)
        self.assertEqual(self.conflicts(), [])

    def test_whitespace_and_case_that_normalise_identically_are_a_replay(self):
        record_event(self.db, send())
        again = record_event(self.db, send(company="  Acme Ltd ", channel="email "))
        self.assertEqual(again["status"], "IDEMPOTENT_REPLAY")

    def test_metadata_is_annotation_not_identity(self):
        """Where a file was imported from is not part of the fact."""
        record_event(self.db, send(metadata={"source_file": "a.csv"}))
        again = record_event(self.db, send(metadata={"source_file": "b.csv"}))
        self.assertEqual(again["status"], "IDEMPOTENT_REPLAY")


class DifferentPayloadIsAConflict(Case):
    def assert_conflict(self, field, changed):
        record_event(self.db, send())
        with self.assertRaises(EventError) as ctx:
            record_event(self.db, send(**changed))
        self.assertEqual(ctx.exception.code, "idempotency_conflict")
        self.assertIn(field, str(ctx.exception))
        stored = effective_events(self.db)
        self.assertEqual(len(stored), 1)
        self.assertEqual(stored[0]["occurred_at"], "2026-09-01", "the original must not be overwritten")
        audit = self.conflicts()
        self.assertEqual(len(audit), 1)
        self.assertIn(field, audit[0]["differing_fields"])
        self.assertEqual(audit[0]["event_id"], stored[0]["event_id"])

    def test_a_different_occurred_at(self):
        self.assert_conflict("occurred_at", {"occurred_at": "2026-09-02"})

    def test_a_different_company(self):
        self.assert_conflict("company", {"company": "Beta Ltd"})

    def test_a_different_buyer(self):
        self.assert_conflict("person_id", {"person_id": "P-02"})

    def test_a_different_experiment(self):
        self.assert_conflict("experiment_id", {"experiment_id": "EXP-ACQ-0010"})

    def test_a_different_campaign(self):
        self.assert_conflict("campaign_id", {"campaign_id": "CMP-2"})

    def test_a_different_provenance(self):
        self.assert_conflict("provenance", {"provenance": "operator_recorded"})

    def test_a_different_channel(self):
        self.assert_conflict("channel", {"channel": "linkedin"})

    def test_a_conflict_is_audited_even_though_the_write_is_refused(self):
        """The refusal rolls back its own transaction; the audit row must survive it."""
        record_event(self.db, send())
        for day in ("2026-09-02", "2026-09-03"):
            with self.assertRaises(EventError):
                record_event(self.db, send(occurred_at=day))
        self.assertEqual(len(self.conflicts()), 2)

    def test_the_audit_trail_is_append_only(self):
        record_event(self.db, send())
        with self.assertRaises(EventError):
            record_event(self.db, send(occurred_at="2026-09-02"))
        con = sqlite3.connect(self.db)
        self.addCleanup(con.close)
        with self.assertRaises(sqlite3.DatabaseError):
            con.execute("DELETE FROM idempotency_conflicts")
        with self.assertRaises(sqlite3.DatabaseError):
            con.execute("UPDATE idempotency_conflicts SET differing_fields = '[]'")


class PaymentReplays(Case):
    def test_a_replayed_payment_with_the_same_amount_is_one_payment(self):
        first = ingest(self.db, StripeAdapter(), [stripe_payment(150_000)])
        again = ingest(self.db, StripeAdapter(), [stripe_payment(150_000, event_id="evt_retry")])
        self.assertEqual((first["inserted"], again["inserted"], again["already_present"]), (1, 0, 1))
        self.assertEqual(again["rejected"], [])

    def test_the_same_payment_intent_with_another_amount_is_refused_and_audited(self):
        ingest(self.db, StripeAdapter(), [stripe_payment(150_000)])
        again = ingest(self.db, StripeAdapter(), [stripe_payment(15_000, event_id="evt_2")])
        self.assertEqual(again["inserted"], 0)
        self.assertEqual([r["code"] for r in again["rejected"]], ["idempotency_conflict"])
        payments = [e for e in effective_events(self.db) if e["event_type"] == "payment_received"]
        self.assertEqual([p["value_pence"] for p in payments], [150_000], "revenue must not change")
        self.assertIn("value_pence", self.conflicts()[0]["differing_fields"])

    def test_the_same_payment_intent_in_another_currency_is_refused(self):
        ingest(self.db, StripeAdapter(), [stripe_payment(150_000)])
        other = stripe_payment(150_000)
        other["data"]["object"]["currency"] = "usd"
        again = ingest(self.db, StripeAdapter(), [other])
        self.assertEqual([r["code"] for r in again["rejected"]], ["idempotency_conflict"])
        self.assertIn("currency", self.conflicts()[0]["differing_fields"])


if __name__ == "__main__":
    unittest.main()
