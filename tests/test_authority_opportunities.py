from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from ai_growth_engineering import registries
from ai_growth_engineering.authority_opportunities import AuthorityOpportunity, readout
from ai_growth_engineering.models import Evidence, EvidenceKind
from ai_growth_engineering.registry import add_evidence
from ai_growth_engineering.storage import connect, init_db


class AuthorityOpportunities(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.db = str(Path(self.tmp.name) / "growth.db")
        init_db(self.db)
        add_evidence(self.db, Evidence("EV-MARKET", EvidenceKind.OBSERVATION, "buyers ask for a decision", "interviews", 0.9))
        add_evidence(self.db, Evidence("EV-PROOF", EvidenceKind.EXPERIMENT, "the bounded test produced a measured result", "experiment", 0.95))
        add_evidence(self.db, Evidence("EV-INFERRED", EvidenceKind.INFERENCE, "an analyst suspects demand", "analysis", 0.95, observed=False))
        registries.add(self.db, "markets", {"market_id": "MKT-1", "hypothesis": "h", "buyer": "Operations lead"})
        registries.add(self.db, "offers", {"offer_id": "OFF-1", "buyer": "Operations lead", "problem": "manual work", "outcome": "faster decisions"})
        registries.add(self.db, "channels", {"channel_id": "CH-1", "name": "Professional network"})
        registries.add(self.db, "claims", {"claim_id": "CLM-1", "statement": "A bounded control changed this measured outcome", "evidence_id": "EV-PROOF"})

    def record(self, **changes):
        row = {
            "authority_opportunity_id": "AUTH-1", "market_id": "MKT-1", "buyer": "Operations lead",
            "problem": "manual work", "information_gap": "available answers lack measured evidence",
            "authority_supply": "many summaries, few reproducible tests", "topic": "What the test changed",
            "topic_class": "evidence", "thesis": "A bounded control changed this measured outcome",
            "proposed_asset": "technical report", "conversion_event": "qualified_conversation",
            "market_evidence_ids": "EV-MARKET", "proof_evidence_ids": "EV-PROOF",
            "claim_ids": "CLM-1", "channel_ids": "CH-1", "offer_id": "OFF-1",
            "content_id": "CONTENT-1", "asset_tier": "proprietary_authority_asset",
            "commercial_buyer_value": 4, "problem_urgency": 4,
            "existing_spend_signal": 3, "information_demand": 4, "answer_quality_gap": 4,
            "evidence_availability": 5, "right_to_win": 4, "distribution_access": 3,
            "product_adjacency": 4, "status": "research",
        }
        row.update(changes)
        registries.add(self.db, "authority_opportunities", row)

    def test_complete_opportunity_is_ranked_and_keeps_claim_to_evidence_lineage(self):
        self.record()
        row = readout(self.db)["opportunities"][0]
        self.assertEqual((row["status"], row["priority"], row["missing"]), ("READY", 35, []))
        thesis = next(stage for stage in row["graph"] if stage["stage"] == "thesis")
        proof = next(stage for stage in row["graph"] if stage["stage"] == "proof")
        self.assertEqual(thesis["items"][0]["id"], "CLM-1")
        self.assertEqual(proof["items"][0]["id"], "EV-PROOF")
        self.assertEqual(row["authority"], "R3_APPROVAL_REQUIRED")
        self.assertEqual(row["asset_tier"], "proprietary_authority_asset")

    def test_high_scores_cannot_compensate_for_missing_market_evidence(self):
        self.record(market_evidence_ids="")
        row = readout(self.db)["opportunities"][0]
        self.assertEqual(row["status"], "RESEARCH")
        self.assertIsNone(row["priority"])
        self.assertIn("market_evidence", row["missing"])
        self.assertIn("before creating more content", row["recommended_action"])
        market = next(stage for stage in row["graph"] if stage["stage"] == "market_evidence")
        self.assertEqual(market["state"], "unknown")

    def test_a_claim_whose_evidence_is_not_linked_is_held(self):
        self.record(proof_evidence_ids="EV-MARKET")
        row = readout(self.db)["opportunities"][0]
        self.assertIn("claim_evidence_not_linked:CLM-1", row["missing"])

    def test_inferred_market_evidence_cannot_unlock_authority(self):
        self.record(market_evidence_ids="EV-INFERRED")
        row = readout(self.db)["opportunities"][0]
        self.assertIn("market_evidence_not_observed:EV-INFERRED", row["missing"])

    def test_a_blocked_claim_cannot_unlock_authority(self):
        registries.add(self.db, "claims", {
            "claim_id": "CLM-BLOCKED", "statement": "unsupported superlative",
            "evidence_id": "EV-PROOF", "status": "rejected",
        })
        self.record(claim_ids="CLM-BLOCKED")
        row = readout(self.db)["opportunities"][0]
        self.assertIn("claim_not_publishable:CLM-BLOCKED", row["missing"])

    def test_unknown_references_are_visible_instead_of_crashing_or_disappearing(self):
        self.record(channel_ids="CH-MISSING")
        row = readout(self.db)["opportunities"][0]
        self.assertIn("unknown_channel:CH-MISSING", row["missing"])
        distribution = next(stage for stage in row["graph"] if stage["stage"] == "distribution")
        self.assertEqual(distribution["items"][0]["label"], "UNKNOWN")

    def test_revenue_is_derived_from_existing_attribution_rows(self):
        self.record()
        registries.add(self.db, "attribution", {"attribution_id": "ATT-1", "source": "content", "revenue_pence": 25000, "content_id": "CONTENT-1"})
        revenue = next(stage for stage in readout(self.db)["opportunities"][0]["graph"] if stage["stage"] == "revenue")
        self.assertEqual((revenue["state"], revenue["items"][0]["revenue_pence"]), ("observed", 25000))

    def test_existing_funnel_populates_each_observed_pre_revenue_stage(self):
        self.record()
        registries.add(self.db, "conversation_funnels", {
            "conversation_funnel_id": "CF-1", "platform": "linkedin",
            "content_id": "CONTENT-1", "primary_cta": "Reply CONTROL",
            "content_views": 100, "qualified_leads": 4, "dm_starts": 3,
            "opportunities": 1,
        })
        stages = {stage["stage"]: stage for stage in readout(self.db)["opportunities"][0]["graph"]}
        for name in ("distribution", "discovery", "qualified_audience", "conversation", "opportunity"):
            self.assertEqual(stages[name]["state"], "observed")
        self.assertEqual(stages["qualified_audience"]["items"][0]["qualified_leads"], 4)

    def test_approved_distribution_and_measured_zero_are_not_confused_with_unknown(self):
        self.record()
        registries.add(self.db, "conversation_funnels", {
            "conversation_funnel_id": "CF-APPROVED", "platform": "linkedin",
            "content_id": "CONTENT-1", "primary_cta": "What fact changes the decision?",
            "distribution_status": "approved", "approved_at": "2026-10-06",
            "authority_opportunity_id": "AUTH-1", "observation_days": 7,
        })
        stages = {stage["stage"]: stage for stage in readout(self.db)["opportunities"][0]["graph"]}
        self.assertEqual(stages["distribution"]["state"], "approved")
        self.assertEqual(stages["conversation"]["state"], "not_observed")
        with connect(self.db) as con:
            con.execute(
                """UPDATE conversation_funnels
                   SET distribution_status = 'observation_complete', published_at = '2026-10-07',
                       observation_ends_at = '2026-10-14', measured_at = '2026-10-14'
                   WHERE conversation_funnel_id = 'CF-APPROVED'"""
            )
        stages = {stage["stage"]: stage for stage in readout(self.db)["opportunities"][0]["graph"]}
        self.assertEqual(stages["distribution"]["state"], "observed")
        self.assertEqual(stages["conversation"]["state"], "observed_zero")

    def test_content_hierarchy_is_closed_and_required(self):
        with self.assertRaisesRegex(ValueError, "asset_tier"):
            self.record(asset_tier="generic_post")

    def test_missing_content_tier_is_held_instead_of_crashing(self):
        self.record()
        with connect(self.db) as con:
            con.execute("UPDATE authority_opportunities SET asset_tier = ''")
        row = readout(self.db)["opportunities"][0]
        self.assertEqual(row["status"], "RESEARCH")
        self.assertIn("asset_tier", row["missing"])

    def test_scores_are_bounded(self):
        with self.assertRaisesRegex(ValueError, "right_to_win must be between 0 and 5"):
            AuthorityOpportunity("AUTH-1", "MKT", "buyer", "problem", "gap", "supply",
                                 "topic", "evidence", "thesis", "asset", "event",
                                 asset_tier="analytical_content", right_to_win=6)


if __name__ == "__main__":
    unittest.main()
