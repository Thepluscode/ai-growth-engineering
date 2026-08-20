from __future__ import annotations

import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from ai_growth_engineering import registries
from ai_growth_engineering.models import Evidence, EvidenceKind, ExperimentSpec
from ai_growth_engineering.registry import (
    add_evidence,
    add_experiment,
    import_outreach,
    record_experiment_result,
)
from ai_growth_engineering.storage import connect, init_db


class RegistryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.db = str(Path(self.tmp.name) / "g.db")
        init_db(self.db)

    def test_every_declared_registry_has_a_table(self):
        # The twelve registries the Digital Marketing architecture requires must all
        # exist. Asserted by name rather than by count so adding a registry does not
        # break the guard, while a missing one still does.
        required = {
            "customer_evidence", "voc", "offers", "proof_inventory", "creatives",
            "channels", "competitor_patterns", "partners", "experiments",
            "revenue_attribution", "economics", "claims",
        }
        self.assertTrue(required <= set(registries.REGISTRY_TABLES),
                        f"missing: {sorted(required - set(registries.REGISTRY_TABLES))}")
        with connect(self.db) as con:
            tables = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        for architecture_name, table in registries.REGISTRY_TABLES.items():
            self.assertIn(table, tables, architecture_name)

    def test_connection_context_closes_the_database(self):
        with connect(self.db) as con:
            con.execute("SELECT 1")
        with self.assertRaises(sqlite3.ProgrammingError):
            con.execute("SELECT 1")

    def test_add_and_read_back(self):
        registries.add(self.db, "offers", {
            "offer_id": "OFF-001", "buyer": "Founder", "problem": "no pipeline",
            "outcome": "qualified conversations", "price_pence": 500_000,
        })
        rows = registries.rows(self.db, "offers")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["price_pence"], 500_000)

    def test_registry_contracts_preserve_required_marketing_fields_and_types(self):
        self.assertTrue({
            "creative_id", "buyer", "problem", "awareness", "angle", "hook",
            "format", "proof", "cta", "experiment_id", "spend_pence",
            "qualified_leads", "opportunities", "revenue_pence",
        } <= set(registries.fields("creatives")))
        self.assertTrue({
            "offer_id", "buyer", "problem", "trigger", "outcome", "price_pence",
            "margin_rate", "proof", "cta", "qualification_criteria",
        } <= set(registries.fields("offers")))
        with connect(self.db) as con:
            attribution_types = {
                row[1]: row[2]
                for row in con.execute("PRAGMA table_info(attribution)")
            }
        self.assertEqual(attribution_types["revenue_pence"], "INTEGER")

    def test_social_conversion_contracts_preserve_funnel_and_ownership_fields(self):
        self.assertTrue({
            "profile_id", "platform", "audience", "positioning", "bio_promise",
            "primary_cta", "pinned_content", "proof_elements", "link_destination",
            "dm_path", "profile_visits", "link_clicks", "dm_starts",
            "qualified_leads", "customers", "revenue_pence", "experiment_id",
        } <= set(registries.fields("social_profiles")))
        self.assertTrue({
            "conversation_funnel_id", "content_id", "engagement_trigger", "dm_path",
            "qualification_criteria", "capture_destination", "owned_contacts",
            "qualified_leads", "opportunities", "customers", "revenue_pence",
        } <= set(registries.fields("conversation_funnels")))
        self.assertTrue({
            "audience_segment_id", "qualified_social_interactions", "owned_contacts",
            "capture_destination", "customers", "revenue_pence",
        } <= set(registries.fields("audience_ownership")))
        self.assertTrue({
            "value_ladder_id", "buyer", "entry_offer_id", "core_offer_id",
            "premium_offer_id", "recurring_offer_id", "expansion_offer_id",
        } <= set(registries.fields("value_ladders")))

        registries.add(self.db, "conversation_funnels", {
            "conversation_funnel_id": "CF-001", "platform": "linkedin",
            "content_id": "POST-001", "primary_cta": "Reply AUDIT",
            "content_views": 1_000, "dm_starts": 25, "qualified_leads": 5,
            "revenue_pence": 250_000,
        })
        row = registries.rows(self.db, "conversation_funnels")[0]
        self.assertEqual(row["content_views"], 1_000)
        self.assertEqual(row["revenue_pence"], 250_000)

    def test_attribution_links_content_through_conversation_to_revenue(self):
        registries.add(self.db, "attribution", {
            "attribution_id": "ATT-001", "source": "social",
            "content_id": "POST-001", "profile_id": "PRO-001",
            "conversation_funnel_id": "CF-001", "audience_segment_id": "AUD-001",
            "offer_id": "OFF-001", "customer": "CUS-001",
            "touchpoint_path": "view>profile>dm>lead>customer", "revenue_pence": 100_000,
        })
        row = registries.rows(self.db, "attribution")[0]
        self.assertEqual(row["content_id"], "POST-001")
        self.assertEqual(row["conversation_funnel_id"], "CF-001")

    def test_missing_required_field_is_rejected(self):
        with self.assertRaises(ValueError):
            registries.add(self.db, "offers", {"offer_id": "OFF-002", "buyer": "Founder"})

    def test_unknown_field_is_rejected_not_dropped(self):
        # A registry that silently discards what it was given is worse than none.
        with self.assertRaises(ValueError):
            registries.add(self.db, "creatives", {
                "creative_id": "CR-1", "buyer": "b", "problem": "p", "hook": "h",
                "vibe": "energetic",
            })

    def test_unknown_registry_is_rejected(self):
        with self.assertRaises(ValueError):
            registries.add(self.db, "vibes", {"x": 1})


class ExperimentContractTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.db = str(Path(self.tmp.name) / "g.db")
        init_db(self.db)

    def test_full_contract_persists(self):
        add_evidence(self.db, Evidence(
            evidence_id="E-001",
            kind=EvidenceKind.OBSERVATION,
            statement="Feature-led hooks dominate the current ads",
            source="https://example.com/ad-library",
            confidence=0.9,
            inference="Proof-led hooks may improve qualified response",
            observed_at="2026-08-19",
            commercial_implication="Test proof before increasing spend",
        ))
        add_experiment(self.db, ExperimentSpec(
            experiment_id="EXP-PAID-0001",
            hypothesis="proof-led hooks beat feature hooks",
            primary_metric="qualified_leads",
            success_threshold=0.10, review_threshold=0.05, minimum_sample=200,
            market="UK SME", buyer="Ops lead", problem="lead quality", channel="meta",
            control="feature hook", variant="proof hook",
            secondary_metrics=("ctr", "cpl"), economic_metric="contribution_profit",
            budget_pence=250_000, start_date="2026-09-01", end_date="2026-09-30",
            evidence_ids=("E-001",),
        ))
        with connect(self.db) as con:
            row = con.execute(
                "SELECT * FROM experiments WHERE experiment_id='EXP-PAID-0001'"
            ).fetchone()
        self.assertEqual(row["channel"], "meta")
        self.assertEqual(row["secondary_metrics"], "ctr; cpl")
        self.assertEqual(row["budget_pence"], 250_000)
        self.assertEqual(row["economic_metric"], "contribution_profit")
        with connect(self.db) as con:
            evidence_ids = [
                item["evidence_id"]
                for item in con.execute(
                    "SELECT evidence_id FROM experiment_evidence WHERE experiment_id=?",
                    ("EXP-PAID-0001",),
                )
            ]
        self.assertEqual(evidence_ids, ["E-001"])

        decision = record_experiment_result(
            self.db,
            "EXP-PAID-0001",
            sample_size=200,
            observed_value=0.12,
            learning="Proof-led hooks increased qualified leads at viable economics",
        )
        self.assertEqual(decision, "keep")
        with connect(self.db) as con:
            result = con.execute(
                "SELECT decision, learning FROM experiments WHERE experiment_id='EXP-PAID-0001'"
            ).fetchone()
        self.assertEqual(result["decision"], "keep")
        self.assertIn("viable economics", result["learning"])

    def test_offer_namespace_is_supported(self):
        add_experiment(
            self.db,
            ExperimentSpec("EXP-OFFER-0001", "h", "m", 0.1, 0.05, 10),
        )

    def test_social_conversion_namespaces_are_supported(self):
        for namespace in ("SOCIAL", "PROFILE", "CONVERSATION"):
            add_experiment(
                self.db,
                ExperimentSpec(f"EXP-{namespace}-0001", "h", "m", 0.1, 0.05, 10),
            )

    def test_contract_fields_are_optional(self):
        # Anything preregistered before the contract existed must stay valid.
        add_experiment(self.db, ExperimentSpec("EXP-ACQ-0001", "h", "m", 0.1, 0.05, 50))

    def test_end_before_start_is_rejected(self):
        with self.assertRaises(ValueError):
            ExperimentSpec("EXP-SEO-0001", "h", "m", 0.1, 0.05, 10,
                           start_date="2026-09-10", end_date="2026-09-01").validate()

    def test_malformed_dates_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "YYYY-MM-DD"):
            ExperimentSpec(
                "EXP-SEO-0001", "h", "m", 0.1, 0.05, 10, start_date="01/09/2026"
            ).validate()

    def test_partial_sample_preserves_no_conclusion(self):
        add_experiment(self.db, ExperimentSpec("EXP-ACQ-0001", "h", "m", 0.1, 0.05, 50))
        decision = record_experiment_result(self.db, "EXP-ACQ-0001", 10, 0.0)
        self.assertEqual(decision, "preregistered")

    def test_negative_sample_is_rejected(self):
        add_experiment(self.db, ExperimentSpec("EXP-ACQ-0001", "h", "m", 0.1, 0.05, 50))
        with self.assertRaises(ValueError):
            record_experiment_result(self.db, "EXP-ACQ-0001", -1, 0.0)

    def test_migration_upgrades_an_existing_database(self):
        """A database created before the contract must gain the columns, not error."""
        legacy = str(Path(self.tmp.name) / "legacy.db")
        con = sqlite3.connect(legacy)
        con.executescript(
            """CREATE TABLE experiments (
                 experiment_id TEXT PRIMARY KEY, hypothesis TEXT NOT NULL,
                 primary_metric TEXT NOT NULL, success_threshold REAL NOT NULL,
                 kill_threshold REAL NOT NULL, minimum_sample INTEGER NOT NULL,
                 decision TEXT NOT NULL DEFAULT 'preregistered',
                 sample_size INTEGER NOT NULL DEFAULT 0, observed_value REAL);
               INSERT INTO experiments(experiment_id, hypothesis, primary_metric,
                 success_threshold, kill_threshold, minimum_sample)
               VALUES ('EXP-ACQ-0001','old','reply',0.1,0.05,50);"""
        )
        con.commit()
        con.close()

        init_db(legacy)  # must migrate in place

        with connect(legacy) as c:
            cols = {r[1] for r in c.execute("PRAGMA table_info(experiments)")}
            self.assertIn("channel", cols)
            self.assertIn("budget_pence", cols)
            tables = {
                row[0]
                for row in c.execute("SELECT name FROM sqlite_master WHERE type='table'")
            }
            self.assertIn("experiment_evidence", tables)
            # the pre-existing row survives
            self.assertEqual(
                c.execute("SELECT hypothesis FROM experiments").fetchone()["hypothesis"], "old"
            )

    def test_migration_adds_social_attribution_fields_to_existing_registry(self):
        legacy = str(Path(self.tmp.name) / "legacy-registry.db")
        con = sqlite3.connect(legacy)
        con.execute(
            """CREATE TABLE attribution (
                 attribution_id TEXT PRIMARY KEY, source TEXT NOT NULL,
                 revenue_pence INTEGER NOT NULL, created_at TEXT NOT NULL
               )"""
        )
        con.commit()
        con.close()

        init_db(legacy)

        with connect(legacy) as c:
            cols = {row[1] for row in c.execute("PRAGMA table_info(attribution)")}
        self.assertTrue({
            "content_id", "profile_id", "conversation_funnel_id",
            "audience_segment_id", "touchpoint_path",
        } <= cols)


class EvidenceContractTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.db = str(Path(self.tmp.name) / "g.db")
        init_db(self.db)

    def test_observation_inference_and_implication_persist_separately(self):
        add_evidence(self.db, Evidence(
            evidence_id="E-001",
            kind=EvidenceKind.OBSERVATION,
            statement="Pricing is absent from the public offer page",
            source="https://example.com/offer",
            confidence=0.95,
            inference="Price uncertainty may suppress enquiries",
            observed_at="2026-08-19",
            commercial_implication="Test a qualified price anchor",
        ))
        with connect(self.db) as con:
            row = con.execute("SELECT * FROM evidence WHERE evidence_id='E-001'").fetchone()
        self.assertEqual(row["statement"], "Pricing is absent from the public offer page")
        self.assertEqual(json.loads(row["metadata_json"]), {})
        self.assertEqual(row["inference"], "Price uncertainty may suppress enquiries")
        self.assertEqual(row["observed_at"], "2026-08-19")
        self.assertEqual(row["commercial_implication"], "Test a qualified price anchor")

    def test_social_voc_metadata_survives_storage(self):
        add_evidence(self.db, Evidence(
            evidence_id="VOC-001",
            kind=EvidenceKind.CUSTOMER_QUOTE,
            statement="I cannot tell which package includes implementation",
            source="social_dm",
            confidence=0.9,
            metadata={
                "audience": "operations leaders",
                "problem": "offer ambiguity",
                "trigger": "pricing post",
                "fear": "buying the wrong scope",
                "desired_outcome": "clear implementation path",
                "objection": "unclear inclusions",
                "exact_language": "which package includes implementation?",
                "commercial_intent": "high",
            },
        ))
        with connect(self.db) as con:
            row = con.execute(
                "SELECT metadata_json FROM evidence WHERE evidence_id='VOC-001'"
            ).fetchone()
        metadata = json.loads(row["metadata_json"])
        self.assertEqual(metadata["commercial_intent"], "high")
        self.assertEqual(metadata["problem"], "offer ambiguity")


class OutreachImportTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.db = str(Path(self.tmp.name) / "g.db")
        init_db(self.db)
        self.csv = Path(self.tmp.name) / "outreach.csv"
        self.csv.write_text(
            "date_first_contact,company,recipient,meaningful_reply,notes\n"
            "2026-08-19,Acme,Jo,,sent\n"
            "2026-08-19,Beta,Sam,yes,replied\n"
            ",Gamma,Kim,,no send date\n",
            encoding="utf-8",
        )

    def test_import_counts_only_real_sends(self):
        imported, skipped = import_outreach(self.db, str(self.csv))
        self.assertEqual((imported, skipped), (2, 1))

    def test_import_is_idempotent(self):
        import_outreach(self.db, str(self.csv))
        imported, _ = import_outreach(self.db, str(self.csv))
        self.assertEqual(imported, 0)
        with connect(self.db) as con:
            self.assertEqual(con.execute("SELECT COUNT(*) FROM outreach").fetchone()[0], 2)

    def test_replies_are_carried_across(self):
        import_outreach(self.db, str(self.csv))
        with connect(self.db) as con:
            total = con.execute("SELECT SUM(meaningful_reply) FROM outreach").fetchone()[0]
        self.assertEqual(total, 1)


if __name__ == "__main__":
    unittest.main()


class NoKillVerdictTests(unittest.TestCase):
    """The system reports what the numbers say; it does not pronounce on the business."""

    def test_kill_is_not_a_decision_the_system_can_reach(self):
        from ai_growth_engineering.models import ExperimentDecision
        values = {d.value for d in ExperimentDecision}
        self.assertNotIn("kill", values)
        self.assertIn("review", values)

    def test_below_threshold_returns_review_not_kill(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        db = str(Path(tmp.name) / "g.db")
        init_db(db)
        add_experiment(db, ExperimentSpec("EXP-ACQ-0002", "h", "reply", 0.10, 0.05, 50))
        self.assertEqual(record_experiment_result(db, "EXP-ACQ-0002", 60, 0.01), "review")

    def test_legacy_kill_rows_and_column_are_migrated(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        db = str(Path(tmp.name) / "legacy.db")
        con = sqlite3.connect(db)
        con.executescript(
            """CREATE TABLE experiments (
                 experiment_id TEXT PRIMARY KEY, hypothesis TEXT NOT NULL,
                 primary_metric TEXT NOT NULL, success_threshold REAL NOT NULL,
                 kill_threshold REAL NOT NULL, minimum_sample INTEGER NOT NULL,
                 decision TEXT NOT NULL DEFAULT 'preregistered',
                 sample_size INTEGER DEFAULT 0, observed_value REAL);
               INSERT INTO experiments VALUES
                 ('EXP-ACQ-0001','h','reply',0.10,0.05,50,'kill',60,0.01);"""
        )
        con.commit()
        con.close()

        init_db(db)

        with connect(db) as c:
            cols = {r[1] for r in c.execute("PRAGMA table_info(experiments)")}
            row = c.execute("SELECT decision, review_threshold FROM experiments").fetchone()
        self.assertIn("review_threshold", cols)
        self.assertNotIn("kill_threshold", cols)
        self.assertEqual(row["decision"], "review")
        self.assertEqual(row["review_threshold"], 0.05)  # the number is unchanged
