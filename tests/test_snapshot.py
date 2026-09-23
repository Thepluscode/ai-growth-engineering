"""Numbers in documentation are generated from state, and a check fails when they drift.

The survey of 2026-09-17 found thirteen documented figures the store contradicted: "180
capabilities" in three files against 215 in the map, "zero invitations sent" against 38 submitted.
Nobody had lied; each number was true once and was then retyped rather than regenerated.

`age snapshot` writes a PII-free state file. Prose carries a figure only inside a
`<!-- state:KEY -->value<!-- /state -->` marker, and `scripts/docs_check.py` fails when a marker,
the capability section or — where a local store exists — the store section disagrees with reality.
"""
from __future__ import annotations

import json
import re
import sys
import tempfile
import unittest
from pathlib import Path

from ai_growth_engineering import capabilities
from ai_growth_engineering.funnel_events import effective_events, record_event
from ai_growth_engineering.models import ExperimentSpec
from ai_growth_engineering.registry import add_experiment
from ai_growth_engineering.snapshot import capability_state, flatten, snapshot, store_state
from ai_growth_engineering.storage import init_db

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import docs_check  # noqa: E402


class Case(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.db = str(self.root / "g.db")
        init_db(self.db)
        add_experiment(self.db, ExperimentSpec("EXP-ACQ-0009", "h", "reply_rate", 0.1, 0.05, 3))
        for i, company in enumerate(("Acme", "Beta")):
            record_event(self.db, {"event_type": "message_sent", "company": company, "person_id": f"jane{i}@acme.co.uk",
                                   "experiment_id": "EXP-ACQ-0009", "occurred_at": "2026-09-01", "source": "t",
                                   "source_record_id": f"r{i}", "provenance": "operator_recorded"})


class Snapshot(Case):
    def test_capabilities_are_counted_from_the_map_itself(self):
        state = capability_state()
        totals = capabilities.counts(capabilities.load())
        self.assertEqual(state["total"], sum(totals.values()))
        self.assertEqual(state["IMPLEMENTED"], totals["IMPLEMENTED"])
        self.assertEqual(state["domains"], len(capabilities.load()["domains"]))

    def test_store_counts_are_the_effective_events(self):
        store = store_state(self.db)
        self.assertEqual(store["events"]["effective"], len(effective_events(self.db)))
        self.assertEqual(store["events"]["by_experiment"]["EXP-ACQ-0009"]["message_sent"], 2)
        exp = store["experiments"]["EXP-ACQ-0009"]
        self.assertEqual((exp["computed_sample"], exp["stored_sample"], exp["execution"]), (2, 0, "EXECUTABLE"))

    def test_the_snapshot_carries_no_person_company_or_address(self):
        text = json.dumps(snapshot(self.db))
        for leaked in ("Acme", "Beta", "jane0", "@acme.co.uk"):
            self.assertNotIn(leaked, text)

    def test_the_snapshot_is_deterministic(self):
        self.assertEqual(json.dumps(snapshot(self.db), sort_keys=True), json.dumps(snapshot(self.db), sort_keys=True))

    def test_the_event_log_hash_moves_when_the_log_moves(self):
        before = store_state(self.db)["events"]["log_sha256"]
        record_event(self.db, {"event_type": "message_sent", "company": "Gamma", "experiment_id": "EXP-ACQ-0009",
                               "occurred_at": "2026-09-02", "source": "t", "source_record_id": "r9",
                               "provenance": "operator_recorded"})
        self.assertNotEqual(store_state(self.db)["events"]["log_sha256"], before)

    def test_an_absent_private_store_is_unavailable_not_empty(self):
        # A fresh clone has no .age/growth.db. Repository state must still generate; the store
        # half must say UNAVAILABLE rather than zeros, and reading it must not create one.
        absent = self.root / "private" / "growth.db"
        state = snapshot(str(absent))
        self.assertEqual(state["local_only_operational"], "UNAVAILABLE")
        self.assertNotIn("store", state)
        self.assertEqual(state["capabilities"], capability_state())
        self.assertFalse(absent.exists())
        self.assertFalse(absent.parent.exists())

    def test_a_present_store_is_available(self):
        state = snapshot(self.db)
        self.assertEqual(state["local_only_operational"], "AVAILABLE")
        self.assertEqual(state["store"], store_state(self.db))

    def test_flatten_gives_dotted_keys(self):
        flat = flatten({"a": {"b": 1, "c": {"d": "x"}}})
        self.assertEqual(flat, {"a.b": 1, "a.c.d": "x"})


class DocsCheck(Case):
    def write_state(self, **overrides):
        state = snapshot(self.db)
        state.update(overrides)
        path = self.root / "STATE.json"
        path.write_text(json.dumps(state, indent=2, sort_keys=True), encoding="utf-8")
        return path

    def doc(self, body):
        path = self.root / "doc.md"
        path.write_text(body, encoding="utf-8")
        return path

    def test_a_marker_that_matches_passes(self):
        state = self.write_state()
        total = capability_state()["total"]
        doc = self.doc(f"We map <!-- state:capabilities.total -->{total}<!-- /state --> capabilities.\n")
        self.assertEqual(docs_check.check_markers([doc], json.loads(state.read_text())), [])

    def test_a_retyped_number_fails(self):
        state = self.write_state()
        doc = self.doc("We map <!-- state:capabilities.total -->180<!-- /state --> capabilities.\n")
        problems = docs_check.check_markers([doc], json.loads(state.read_text()))
        self.assertEqual(len(problems), 1)
        self.assertIn("capabilities.total", problems[0])

    def test_an_unknown_key_fails(self):
        state = self.write_state()
        doc = self.doc("<!-- state:capabilities.nonsense -->1<!-- /state -->\n")
        self.assertTrue(docs_check.check_markers([doc], json.loads(state.read_text())))

    def test_sync_rewrites_marker_values_from_the_state(self):
        state = self.write_state()
        doc = self.doc("x <!-- state:capabilities.total -->180<!-- /state --> y\n")
        docs_check.sync_markers([doc], json.loads(state.read_text()))
        self.assertEqual(re.findall(r"-->(.*?)<!--", doc.read_text())[0], str(capability_state()["total"]))

    def test_a_stale_capability_section_fails_without_any_store(self):
        stale = dict(capability_state(), total=180)
        self.assertTrue(docs_check.check_capabilities({"capabilities": stale}))
        self.assertEqual(docs_check.check_capabilities({"capabilities": capability_state()}), [])

    def test_a_stale_store_section_fails_when_a_store_exists(self):
        state = snapshot(self.db)
        record_event(self.db, {"event_type": "message_sent", "company": "Gamma", "experiment_id": "EXP-ACQ-0009",
                               "occurred_at": "2026-09-02", "source": "t", "source_record_id": "r9",
                               "provenance": "operator_recorded"})
        problems, checked = docs_check.check_store(state, self.db)
        self.assertTrue(checked)
        self.assertTrue(problems)

    def test_no_store_is_reported_as_not_checked_never_as_a_pass(self):
        problems, checked = docs_check.check_store(snapshot(self.db), str(self.root / "absent.db"))
        self.assertEqual((problems, checked), ([], False))

    def test_store_markers_are_not_checked_when_the_store_is_unavailable(self):
        state = snapshot(str(self.root / "absent.db"))
        doc = self.doc("<!-- state:store.events.effective -->7<!-- /state -->\n")
        self.assertEqual(docs_check.check_markers([doc], state), [])
        self.assertEqual(docs_check.unchecked_store_markers([doc], state), 1)
        # Only the store half is exempt; a wrong repository figure still fails.
        doc = self.doc("<!-- state:capabilities.total -->1<!-- /state -->\n")
        self.assertTrue(docs_check.check_markers([doc], state))

    def test_store_markers_are_checked_when_the_store_is_available(self):
        doc = self.doc("<!-- state:store.events.effective -->7<!-- /state -->\n")
        self.assertTrue(docs_check.check_markers([doc], snapshot(self.db)))

    def test_the_repository_itself_is_consistent(self):
        state = json.loads((ROOT / "docs" / "STATE.json").read_text(encoding="utf-8"))
        self.assertEqual(docs_check.check_capabilities(state), [])
        markers = docs_check.tracked_markdown(ROOT)
        self.assertEqual(docs_check.check_markers(markers, state), [])
        self.assertGreaterEqual(docs_check.marker_count(markers), docs_check.MIN_MARKERS)

    def test_a_tracker_status_outside_the_ladder_fails(self):
        doc = self.doc("| Capability | Status | Evidence |\n| --- | --- | --- |\n"
                       "| A | VERIFIED LOCAL (synthetic) | tests |\n| B | TESTED | tests |\n")
        problems = docs_check.check_tracker(doc)
        self.assertEqual(len(problems), 1)
        self.assertIn("VERIFIED LOCAL", problems[0])

    def test_the_repository_tracker_uses_only_the_ladder(self):
        self.assertEqual(docs_check.check_tracker(ROOT / "FEATURE_TRACKER.md"), [])

    def test_the_selftest_runs_its_own_controls(self):
        self.assertEqual(docs_check.selftest(), 0)


if __name__ == "__main__":
    unittest.main()
