"""Market layer on synthetic stores. Expected counts are hard-coded from the events each case
records, never recomputed through the module under test."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from ai_growth_engineering import registries
from ai_growth_engineering.funnel_events import correct_event, record_event
from ai_growth_engineering.markets import (COMPARABLE, NOT_ENOUGH_EVIDENCE, TESTED, UNTESTED,
                                           MarketError, compare, layer_evidence)
from ai_growth_engineering.storage import init_db


class MarketCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.db = str(Path(self.tmp.name) / "growth.db")
        init_db(self.db)
        self.n = 0
        for market in ("MKT-A", "MKT-B"):
            registries.add(self.db, "markets", {"market_id": market, "hypothesis": f"{market} has the problem"})

    def link(self, market, experiment, layer, protocol, exposure="message_sent", positive="reply_meaningful"):
        self.n += 1
        registries.add(self.db, "market_experiments", {
            "link_id": f"L{self.n}", "market_id": market, "experiment_id": experiment, "layer": layer,
            "protocol": protocol, "exposure_event": exposure, "positive_event": positive})

    def events(self, experiment, event_type, n, *, provenance="operator_recorded"):
        ids = []
        for i in range(n):
            self.n += 1
            ids.append(record_event(self.db, {
                "event_type": event_type, "company": f"{experiment}-co{i}", "experiment_id": experiment,
                "source": "test", "source_record_id": f"r{self.n}", "provenance": provenance,
                "occurred_at": "2026-09-01T00:00:00+00:00"})["event_id"])
        return ids


class LayerEvidence(MarketCase):
    def test_counts_come_from_the_event_log(self):
        self.link("MKT-A", "EXP-1", "DEMAND", "cold-email-v1")
        self.events("EXP-1", "message_sent", 40)
        self.events("EXP-1", "reply_meaningful", 3)
        demand = layer_evidence(self.db, "MKT-A")["DEMAND"]
        self.assertEqual(demand["status"], TESTED)
        self.assertEqual(demand["protocols"]["cold-email-v1"],
                         {"experiments": ["EXP-1"], "exposures": 40, "positives": 3})

    def test_tested_access_says_nothing_about_demand(self):
        self.link("MKT-A", "EXP-1", "ACCESS", "invite-v1", "invitation_sent", "invitation_accepted")
        self.events("EXP-1", "invitation_sent", 30)
        self.events("EXP-1", "invitation_accepted", 12)
        layers = layer_evidence(self.db, "MKT-A")
        self.assertEqual(layers["ACCESS"]["status"], TESTED)
        for layer in ("RESEARCH", "DEMAND", "COMMERCIAL", "PAID"):
            self.assertEqual(layers[layer], {"status": UNTESTED, "protocols": {}}, layer)

    def test_a_market_with_no_links_is_untested_everywhere(self):
        self.assertTrue(all(v["status"] == UNTESTED for v in layer_evidence(self.db, "MKT-B").values()))

    def test_corrected_events_are_not_counted(self):
        self.link("MKT-A", "EXP-1", "DEMAND", "cold-email-v1")
        self.events("EXP-1", "message_sent", 10)
        wrong = self.events("EXP-1", "reply_meaningful", 2)
        correct_event(self.db, wrong[0], "not a meaningful reply")
        self.assertEqual(layer_evidence(self.db, "MKT-A")["DEMAND"]["protocols"]["cold-email-v1"]["positives"], 1)

    def test_synthetic_fixtures_are_not_market_evidence(self):
        self.link("MKT-A", "EXP-1", "DEMAND", "cold-email-v1")
        self.events("EXP-1", "message_sent", 10, provenance="synthetic_fixture")
        self.assertEqual(layer_evidence(self.db, "MKT-A")["DEMAND"]["protocols"]["cold-email-v1"]["exposures"], 0)

    def test_the_same_protocol_is_summed_and_different_protocols_are_not(self):
        self.link("MKT-A", "EXP-1", "DEMAND", "cold-email-v1")
        self.link("MKT-A", "EXP-2", "DEMAND", "cold-email-v1")
        self.link("MKT-A", "EXP-3", "DEMAND", "linkedin-dm-v1")
        self.events("EXP-1", "message_sent", 10)
        self.events("EXP-2", "message_sent", 15)
        self.events("EXP-3", "message_sent", 7)
        protocols = layer_evidence(self.db, "MKT-A")["DEMAND"]["protocols"]
        self.assertEqual(protocols["cold-email-v1"]["exposures"], 25)
        self.assertEqual(protocols["cold-email-v1"]["experiments"], ["EXP-1", "EXP-2"])
        self.assertEqual(protocols["linkedin-dm-v1"]["exposures"], 7)

    def test_one_fact_cannot_count_in_two_layers(self):
        self.link("MKT-A", "EXP-1", "ACCESS", "invite-v1", "invitation_sent", "invitation_accepted")
        self.link("MKT-A", "EXP-1", "DEMAND", "invite-v1", "invitation_accepted", "reply_meaningful")
        with self.assertRaisesRegex(MarketError, "one fact counts in one layer"):
            layer_evidence(self.db, "MKT-A")

    def test_unknown_market_is_an_error_not_an_empty_answer(self):
        with self.assertRaisesRegex(MarketError, "unknown market"):
            layer_evidence(self.db, "MKT-NOPE")

    def test_an_unknown_layer_is_refused_at_registration(self):
        with self.assertRaisesRegex(ValueError, "layer must be one of"):
            self.link("MKT-A", "EXP-1", "INTEREST", "p")


class Comparison(MarketCase):
    def demand(self, market, experiment, protocol, sent, replies):
        self.link(market, experiment, "DEMAND", protocol)
        self.events(experiment, "message_sent", sent)
        self.events(experiment, "reply_meaningful", replies)

    def test_the_first_answer_with_no_evidence_is_not_enough_evidence(self):
        result = compare(self.db, "MKT-A", "MKT-B", "DEMAND")
        self.assertEqual(result["verdict"], NOT_ENOUGH_EVIDENCE)
        self.assertIn("untested in MKT-A, MKT-B", result["reason"])

    def test_one_side_untested(self):
        self.demand("MKT-A", "EXP-1", "cold-email-v1", 40, 4)
        result = compare(self.db, "MKT-A", "MKT-B", "DEMAND")
        self.assertEqual(result["verdict"], NOT_ENOUGH_EVIDENCE)
        self.assertIn("untested in MKT-B", result["reason"])

    def test_different_protocols_are_never_pooled(self):
        self.demand("MKT-A", "EXP-1", "cold-email-v1", 40, 4)
        self.demand("MKT-B", "EXP-2", "linkedin-dm-v1", 40, 8)
        result = compare(self.db, "MKT-A", "MKT-B", "DEMAND")
        self.assertEqual(result["verdict"], NOT_ENOUGH_EVIDENCE)
        self.assertIn("not pooled", result["reason"])
        self.assertEqual(result["comparisons"], [])

    def test_access_evidence_is_not_compared_as_demand(self):
        self.link("MKT-A", "EXP-1", "ACCESS", "p", "invitation_sent", "invitation_accepted")
        self.link("MKT-B", "EXP-2", "ACCESS", "p", "invitation_sent", "invitation_accepted")
        self.events("EXP-1", "invitation_sent", 40)
        self.events("EXP-2", "invitation_sent", 40)
        self.assertEqual(compare(self.db, "MKT-A", "MKT-B", "DEMAND")["verdict"], NOT_ENOUGH_EVIDENCE)
        self.assertEqual(compare(self.db, "MKT-A", "MKT-B", "ACCESS")["verdict"], COMPARABLE)

    def test_comparable_reports_rates_and_names_no_winner(self):
        self.demand("MKT-A", "EXP-1", "cold-email-v1", 40, 4)
        self.demand("MKT-B", "EXP-2", "cold-email-v1", 50, 10)
        result = compare(self.db, "MKT-A", "MKT-B", "DEMAND")
        self.assertEqual(result["verdict"], COMPARABLE)
        sides = result["comparisons"][0]["sides"]
        self.assertEqual([(s["market"], s["exposures"], s["positives"], s["rate"]) for s in sides],
                         [("MKT-A", 40, 4, 0.1), ("MKT-B", 50, 10, 0.2)])
        self.assertNotIn("winner", result)

    def test_minimum_sample_boundary(self):
        self.demand("MKT-A", "EXP-1", "cold-email-v1", 30, 1)
        self.demand("MKT-B", "EXP-2", "cold-email-v1", 29, 1)
        below = compare(self.db, "MKT-A", "MKT-B", "DEMAND", min_exposures=30)
        self.assertEqual(below["verdict"], NOT_ENOUGH_EVIDENCE)
        self.assertIn("below 30 exposures: MKT-B", below["comparisons"][0]["reason"])
        exactly = compare(self.db, "MKT-A", "MKT-B", "DEMAND", min_exposures=29)
        self.assertEqual(exactly["verdict"], COMPARABLE)

    def test_a_nonsense_minimum_is_clamped_not_trusted(self):
        self.demand("MKT-A", "EXP-1", "p", 1, 0)
        self.demand("MKT-B", "EXP-2", "p", 1, 1)
        result = compare(self.db, "MKT-A", "MKT-B", "DEMAND", min_exposures=-5)
        self.assertEqual(result["min_exposures"], 1)
        self.assertEqual(result["verdict"], COMPARABLE)

    def test_zero_exposures_never_divides(self):
        self.link("MKT-A", "EXP-1", "DEMAND", "p")
        self.link("MKT-B", "EXP-2", "DEMAND", "p")
        result = compare(self.db, "MKT-A", "MKT-B", "DEMAND", min_exposures=1)
        self.assertEqual(result["verdict"], NOT_ENOUGH_EVIDENCE)
        self.assertIsNone(result["comparisons"][0]["sides"][0]["rate"])

    def test_malformed_requests(self):
        with self.assertRaisesRegex(MarketError, "layer must be one of"):
            compare(self.db, "MKT-A", "MKT-B", "demand")
        with self.assertRaisesRegex(MarketError, "itself"):
            compare(self.db, "MKT-A", "MKT-A", "DEMAND")
        with self.assertRaisesRegex(MarketError, "unknown market"):
            compare(self.db, "MKT-A", "MKT-NOPE", "DEMAND")


if __name__ == "__main__":
    unittest.main()
