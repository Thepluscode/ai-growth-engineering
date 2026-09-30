"""The weekly cycle end to end through the real workbench path: draft tagged with a market
experiment -> approve -> record send -> record reply -> market layer and readout. Expected
counts are hard-coded from what each case does."""
from __future__ import annotations

import tempfile
import unittest
from datetime import date
from pathlib import Path

from ai_growth_engineering import registries
from ai_growth_engineering.funnel_events import record_event
from ai_growth_engineering.markets import layer_evidence
from ai_growth_engineering.outbound_workbench import (WorkbenchError, approve_draft, create_draft,
                                                      record_manual_send, record_meaningful_reply)
from ai_growth_engineering.storage import connect, init_db
from ai_growth_engineering.weekly_cycle import readout, render

AS_OF = date(2026, 10, 4)


class Cycle(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.db = str(Path(self.tmp.name) / "g.db")
        init_db(self.db)
        with connect(self.db) as con:
            for pid in range(1, 4):
                con.execute("""INSERT INTO prospects(id, company, website, priority, target_roles, evidence,
                               source_url, status) VALUES (?, ?, 'https://example.com', 'A', 'Head', 'e',
                               'https://example.com', 'qualified')""", (pid, f"Co{pid}"))
        for market, experiment in (("MKT-A", "EXP-A"), ("MKT-B", "EXP-B")):
            registries.add(self.db, "markets", {"market_id": market, "hypothesis": "h", "buyer": "Head"})
            registries.add(self.db, "market_experiments", {
                "link_id": f"L-{experiment}", "market_id": market, "experiment_id": experiment,
                "layer": "DEMAND", "protocol": "named-buyer-message-v1",
                "exposure_event": "message_sent", "positive_event": "reply_meaningful"})

    def draft(self, prospect_id=1, experiment_id="EXP-A", recipient_class="named_buyer", who="buyer1"):
        return create_draft(self.db, {
            "prospect_id": prospect_id, "recipient_identity": f"{who}@example.com",
            "recipient_class": recipient_class, "channel": "email",
            "observation": "Their pricing page has no route for a buyer who is ready to talk now.",
            "economic_hypothesis": "A direct route would turn more ready buyers into conversations each month.",
            "cta": "Want the one-page note?", "metric": "qualified conversations",
            "source_url": "https://example.com/pricing", "experiment_id": experiment_id})

    def send_and_reply(self, draft, sent="2026-10-01T10:00:00+00:00", reply="2026-10-02T10:00:00+00:00"):
        approve_draft(self.db, draft["id"])
        record_manual_send(self.db, draft["id"], sent)
        if reply:
            record_meaningful_reply(self.db, draft["id"], reply)

    def test_a_tagged_draft_is_credited_to_its_market_end_to_end(self):
        self.send_and_reply(self.draft())
        demand = layer_evidence(self.db, "MKT-A")["DEMAND"]["protocols"]["named-buyer-message-v1"]
        self.assertEqual((demand["exposures"], demand["positives"]), (1, 1))
        row = readout(self.db, AS_OF)["markets"][0]
        self.assertEqual((row["market_id"], row["sent"], row["replies"], row["sent_this_week"]),
                         ("MKT-A", 1, 1, 1))
        self.assertEqual(row["status"], "NEEDS_29_MORE")
        self.assertEqual(row["this_week_to_do"], 14)
        self.assertIsNone(row["reply_rate"], "a rate below the minimum sample is not reported")

    def test_drafts_awaiting_send_reduce_this_weeks_to_do(self):
        self.draft(prospect_id=1, who="a")
        approve_draft(self.db, self.draft(prospect_id=2, who="b")["id"])
        row = readout(self.db, AS_OF)["markets"][0]
        self.assertEqual((row["queued"], row["this_week_to_do"]), (2, 13))

    def test_an_untagged_draft_counts_in_no_market(self):
        self.send_and_reply(self.draft(experiment_id=""))
        self.assertEqual(layer_evidence(self.db, "MKT-A")["DEMAND"]["protocols"]
                         ["named-buyer-message-v1"]["exposures"], 0)

    def test_a_role_inbox_is_refused_for_a_market_experiment(self):
        with self.assertRaises(WorkbenchError) as ctx:
            self.draft(recipient_class="role_inbox")
        self.assertEqual(ctx.exception.code, "named_buyer_required")

    def test_an_experiment_linked_to_no_market_is_refused(self):
        with self.assertRaises(WorkbenchError) as ctx:
            self.draft(experiment_id="EXP-NOWHERE")
        self.assertEqual(ctx.exception.code, "experiment_not_linked")

    def test_only_this_weeks_sends_count_toward_this_week(self):
        self.send_and_reply(self.draft(prospect_id=1, who="a"), sent="2026-09-26T10:00:00+00:00", reply="")
        self.send_and_reply(self.draft(prospect_id=2, who="b"), sent="2026-09-28T10:00:00+00:00", reply="")
        row = readout(self.db, AS_OF)["markets"][0]
        self.assertEqual((row["sent"], row["sent_this_week"]), (2, 1))

    def test_reaching_the_minimum_makes_the_market_measurable(self):
        for i in range(30):
            record_event(self.db, {"event_type": "message_sent", "company": f"c{i}", "experiment_id": "EXP-B",
                                   "source": "t", "source_record_id": f"s{i}", "provenance": "operator_recorded",
                                   "occurred_at": "2026-10-01T00:00:00+00:00"})
        record_event(self.db, {"event_type": "reply_meaningful", "company": "c0", "experiment_id": "EXP-B",
                               "source": "t", "source_record_id": "r0", "provenance": "operator_recorded",
                               "occurred_at": "2026-10-02T00:00:00+00:00"})
        row = [m for m in readout(self.db, AS_OF)["markets"] if m["market_id"] == "MKT-B"][0]
        self.assertEqual((row["status"], row["this_week_to_do"], row["reply_rate"]), ("MEASURABLE", 0, 0.0333))

    def test_the_comparison_waits_for_both_markets(self):
        self.send_and_reply(self.draft())
        data = readout(self.db, AS_OF)
        self.assertEqual(data["comparisons"][0]["verdict"], "NOT_ENOUGH_EVIDENCE")
        self.assertIn("NOT_ENOUGH_EVIDENCE", render(data))

    def test_no_markets_says_how_to_register_one(self):
        empty = str(Path(self.tmp.name) / "empty.db")
        init_db(empty)
        data = readout(empty, AS_OF)
        self.assertEqual(data["markets"], [])
        self.assertIn("seeds/registries.json", render(data))

    def test_a_nonsense_target_is_clamped(self):
        self.assertEqual(readout(self.db, AS_OF, weekly_target=0)["weekly_target"], 1)


if __name__ == "__main__":
    unittest.main()
