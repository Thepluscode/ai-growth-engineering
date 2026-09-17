"""One commercial truth: where the event log can compute a figure, the event log is the figure.

The revenue-gate scoreboard summed hand-set counters on the legacy `outreach` table — a tick for a
reply, a tick for a proposal, a typed amount for revenue — while the canonical event log recorded
the same activity independently. The two could disagree and nothing said so; the counter won.

Now every counter the log can derive is computed from it (COMPUTED). The legacy counter stays on
file and is shown beside it as MANUAL_ANNOTATION, flagged when it disagrees. A figure the log has
no event for (diagnostics proposed) is MANUAL_ANNOTATION outright. A store with no canonical events
at all still reports its counters — labelled, never silently promoted.
"""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from ai_growth_engineering.funnel_events import effective_events, record_event
from ai_growth_engineering.outbound_workbench import (
    approve_draft, create_draft, record_manual_send, record_meaningful_reply,
)
from ai_growth_engineering.registry import scoreboard, scoreboard_basis
from ai_growth_engineering.storage import connect, init_db

DRAFT = {"prospect_id": 1, "recipient_identity": "founder@example.com", "recipient_class": "named_buyer",
         "channel": "email",
         "observation": "Your managed-security pages route assessment demand into the general enquiry form.",
         "economic_hypothesis": "That shared path may be suppressing qualified conversations rather than "
                                "traffic being the constraint.",
         "cta": "Want me to send the one-page experiment map?", "metric": "qualified_conversation_rate",
         "source_url": "https://example.com/managed-security"}


class Case(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.db = str(Path(self.tmp.name) / "g.db")
        init_db(self.db)
        self.n = 0

    def ev(self, event_type, company, **kw):
        self.n += 1
        values = {"event_type": event_type, "company": company, "occurred_at": "2026-09-01", "source": "t",
                  "source_record_id": f"r{self.n}", "provenance": "operator_recorded"}
        values.update(kw)
        return record_event(self.db, values)

    def legacy(self, company, **counters):
        cols = {"sent_at": "2026-09-01", **counters}
        with connect(self.db) as con:
            con.execute(f"INSERT INTO outreach(company, {', '.join(cols)}) VALUES (?{', ?' * len(cols)})",
                        (company, *cols.values()))

    def basis(self):
        return {row["metric"]: row for row in scoreboard_basis(self.db)}


class CanonicalIsAuthoritative(Case):
    def test_a_ticked_reply_the_log_never_saw_does_not_count(self):
        self.ev("message_sent", "Acme")
        self.legacy("Acme", meaningful_reply=1)
        self.assertEqual(scoreboard(self.db)["meaningful_responses"], 0)
        row = self.basis()["meaningful_responses"]
        self.assertEqual((row["basis"], row["value"], row["manual"], row["diverges"]), ("COMPUTED", 0, 1, True))

    def test_typed_revenue_does_not_override_recorded_payments(self):
        self.ev("payment_received", "Acme", value_pence=150_000, currency="GBP")
        self.legacy("Acme", paid=1, collected_revenue_pence=999_999)
        values = scoreboard(self.db)
        self.assertEqual((values["collected_revenue_pence"], values["paying_customers"]), (150_000, 1))
        self.assertTrue(self.basis()["collected_revenue_pence"]["diverges"])
        self.assertFalse(self.basis()["paying_customers"]["diverges"])

    def test_each_derivable_counter_comes_from_its_event(self):
        for company in ("A", "B", "C"):
            self.ev("message_sent", company)
        self.ev("message_bounced", "C")
        self.ev("reply_meaningful", "A")
        self.ev("meeting_held", "A")
        self.ev("proposal_sent", "A", value_pence=300_000, currency="GBP")
        values = scoreboard(self.db)
        self.assertEqual((values["outreach_sent"], values["meaningful_responses"], values["discovery_calls"],
                          values["commercial_proposals"], values["paying_customers"], values["collected_revenue_pence"]),
                         (2, 1, 1, 1, 0, 0))

    def test_refunds_net_off_and_one_customer_paying_twice_is_one_customer(self):
        self.ev("payment_received", "Acme", value_pence=100_000, currency="GBP")
        self.ev("payment_received", "Acme", value_pence=50_000, currency="GBP")
        self.ev("refund", "Acme", value_pence=20_000, currency="GBP")
        values = scoreboard(self.db)
        self.assertEqual((values["paying_customers"], values["collected_revenue_pence"]), (1, 130_000))

    def test_synthetic_fixtures_never_reach_the_gate(self):
        self.ev("message_sent", "Real")
        self.ev("payment_received", "Demo", value_pence=500_000, currency="GBP", provenance="synthetic_fixture")
        self.assertEqual(scoreboard(self.db)["collected_revenue_pence"], 0)

    def test_a_figure_the_log_cannot_derive_is_labelled_manual(self):
        self.ev("message_sent", "Acme")
        self.legacy("Acme", diagnostic_proposed=1)
        row = self.basis()["diagnostics_proposed"]
        self.assertEqual((row["basis"], row["value"]), ("MANUAL_ANNOTATION", 1))

    def test_a_store_without_canonical_events_is_labelled_not_promoted(self):
        self.legacy("Legacy", meaningful_reply=1)
        self.assertEqual(scoreboard(self.db)["meaningful_responses"], 1)
        self.assertEqual(self.basis()["meaningful_responses"]["basis"], "MANUAL_ANNOTATION")

    def test_the_scoreboard_command_shows_the_basis_and_the_disagreement(self):
        import contextlib
        import io

        from ai_growth_engineering.cli import build_parser

        self.ev("message_sent", "Acme")
        self.legacy("Acme", meaningful_reply=1)
        args = build_parser().parse_args(["scoreboard", "--db", self.db])
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            args.func(args)
        line = next(l for l in out.getvalue().splitlines() if l.startswith("meaningful_responses"))
        self.assertIn("COMPUTED", line)
        self.assertIn("manual 1", line)


class WritersFeedTheLog(Case):
    def setUp(self):
        super().setUp()
        with connect(self.db) as con:
            con.execute("""INSERT INTO prospects(id, company, website, priority, target_roles, evidence, source_url,
                           status) VALUES (1, 'Acme Security', 'https://example.com', 'A', 'Founder', 'e',
                           'https://example.com', 'qualified')""")

    def test_a_workbench_send_and_reply_are_canonical_events_counted_once(self):
        self.ev("message_sent", "Other Co")  # the log already exists, so it is authoritative
        draft = create_draft(self.db, DRAFT)["id"]
        approve_draft(self.db, draft)
        record_manual_send(self.db, draft, "2026-09-15")
        record_meaningful_reply(self.db, draft, "2026-09-16")
        mine = [e for e in effective_events(self.db) if e["company"] == "Acme Security"]
        self.assertEqual({(e["event_type"], e["occurred_at"]) for e in mine},
                         {("message_sent", "2026-09-15"), ("reply_meaningful", "2026-09-16")})
        self.assertEqual(mine[0]["metadata"]["recipient_class"], "named_buyer")
        values = scoreboard(self.db)
        self.assertEqual((values["outreach_sent"], values["meaningful_responses"]), (2, 1))

    def test_outreach_record_appends_a_canonical_send(self):
        from ai_growth_engineering.cli import build_parser

        args = build_parser().parse_args(["outreach-record", "--db", self.db, "--company", "Acme",
                                          "--identity", "info@acme.test", "--sent-at", "2026-09-15"])
        args.func(args)
        sends = [e for e in effective_events(self.db) if e["event_type"] == "message_sent"]
        self.assertEqual([(e["company"], e["occurred_at"]) for e in sends], [("Acme", "2026-09-15")])

    def test_outreach_record_refuses_undated_pipeline_and_money_flags(self):
        """A proposal, meeting or payment has its own date; a send log cannot supply it."""
        from ai_growth_engineering.cli import build_parser

        for flag in (["--paid"], ["--proposal"], ["--discovery"], ["--collected-revenue", "1500"]):
            args = build_parser().parse_args(["outreach-record", "--db", self.db, "--company", "Acme",
                                              "--identity", "info@acme.test", "--sent-at", "2026-09-15", *flag])
            with self.assertRaises(SystemExit, msg=flag) as ctx:
                args.func(args)
            self.assertIn("event-record", str(ctx.exception))
        with connect(self.db) as con:
            self.assertEqual(con.execute("SELECT COUNT(*) FROM outreach").fetchone()[0], 0)


if __name__ == "__main__":
    unittest.main()
