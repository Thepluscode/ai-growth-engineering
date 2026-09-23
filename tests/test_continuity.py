"""The continuity contract: a fresh session must reconstruct the project from this
repository alone. These tests assert the repository can answer, without any prior
conversation, what the project is and what is authorised now."""
from __future__ import annotations

import json
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PREFLIGHT = Path.home() / ".claude" / "scripts" / "preflight"
ACTIVE = ROOT / "ACTIVE_WORK.yaml"
CONTEXT = ROOT / "AGENT_CONTEXT.md"
BOOTSTRAP = ROOT / "CLAUDE.md"
STATE = ROOT / "docs" / "STATE.json"


def preflight(path):
    out = subprocess.run([sys.executable, str(PREFLIGHT), str(path)],
                         capture_output=True, text=True, timeout=60)
    return out.returncode, out.stdout


class PreflightContract(unittest.TestCase):
    """Exit codes, because a warning nobody reads is not a control."""

    @unittest.skipUnless(PREFLIGHT.exists(), "global preflight not installed")
    def test_a_healthy_canonical_checkout_succeeds(self):
        # Built here, not read from this checkout: whether the live STATE.json is fresh
        # is a fact about the day the suite runs, and asserting it made this test a
        # monitor that went red whenever nobody had run `make snapshot` for 24 hours.
        from datetime import datetime, timezone
        env = {"PATH": "/usr/bin:/bin", "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
               "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"}
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / "repo"
            (repo / "docs").mkdir(parents=True)
            subprocess.run(["git", "init", "-q", str(repo)], check=True)
            (repo / "AGENT_CONTEXT.md").write_text("# charter\n")
            (repo / "ACTIVE_WORK.yaml").write_text("active:\n  task: healthy_task\n")
            subprocess.run(["git", "-C", str(repo), "add", "-A"], check=True)
            subprocess.run(["git", "-C", str(repo), "commit", "-q", "-m", "x", "--no-gpg-sign"],
                           check=True, env={**env, "HOME": tmp})
            head = subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD"],
                                  capture_output=True, text=True, check=True).stdout.strip()
            (repo / "docs" / "STATE.json").write_text(json.dumps({"runtime": {
                "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "git_head": head}}))
            code, text = preflight(repo)
        self.assertEqual(code, 0, text)
        self.assertIn("canonical  yes", text)
        self.assertIn("STATE_OK", text)
        self.assertIn("healthy_task", text)

    def test_this_checkout_names_its_active_task(self):
        # The stable half of the old live assertion: the authority file itself.
        self.assertIn("task: continuity_reference_implementation", ACTIVE.read_text())

    @unittest.skipUnless(PREFLIGHT.exists(), "global preflight not installed")
    def test_the_deviated_age_path_fails_closed(self):
        code, text = preflight(Path.home() / "projects" / "ai-growth-engineering")
        self.assertNotEqual(code, 0)
        self.assertIn("STOP", text)

    @unittest.skipUnless(PREFLIGHT.exists(), "global preflight not installed")
    def test_a_preserved_copy_inside_the_repo_fails_closed(self):
        if not (ROOT / "imports").exists():
            self.skipTest("no imports/ subtree in this checkout")
        code, text = preflight(ROOT / "imports")
        self.assertNotEqual(code, 0)
        self.assertIn("STOP", text)

    @unittest.skipUnless(PREFLIGHT.exists(), "global preflight not installed")
    def test_missing_active_work_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / "repo"
            repo.mkdir()
            subprocess.run(["git", "init", "-q", str(repo)], check=True)
            (repo / "AGENT_CONTEXT.md").write_text("# charter\n")
            code, text = preflight(repo)
            self.assertNotEqual(code, 0, text)
            self.assertIn("MISSING", text)

    @unittest.skipUnless(PREFLIGHT.exists(), "global preflight not installed")
    def test_state_describing_another_commit_is_reported_stale(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / "repo"
            (repo / "docs").mkdir(parents=True)
            subprocess.run(["git", "init", "-q", str(repo)], check=True)
            subprocess.run(["git", "-C", str(repo), "commit", "-q", "--allow-empty",
                            "-m", "x", "--no-gpg-sign"], check=True,
                           env={"PATH": "/usr/bin:/bin", "HOME": tmp,
                                "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
                                "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"})
            (repo / "AGENT_CONTEXT.md").write_text("# charter\n")
            (repo / "ACTIVE_WORK.yaml").write_text("active:\n  task: something\n")
            (repo / "docs" / "STATE.json").write_text(json.dumps({"runtime": {
                "generated_at": "2099-01-01T00:00:00+00:00", "git_head": "0" * 40}}))
            code, text = preflight(repo)
            self.assertNotEqual(code, 0, text)
            # preflight names this case precisely since it split HEAD mismatch from age.
            self.assertIn("STATE_HEAD_MISMATCH", text)

    @unittest.skipUnless(PREFLIGHT.exists(), "global preflight not installed")
    def test_state_that_cannot_prove_its_age_is_not_called_fresh(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / "repo"
            (repo / "docs").mkdir(parents=True)
            subprocess.run(["git", "init", "-q", str(repo)], check=True)
            (repo / "AGENT_CONTEXT.md").write_text("# charter\n")
            (repo / "ACTIVE_WORK.yaml").write_text("active:\n  task: something\n")
            (repo / "docs" / "STATE.json").write_text(json.dumps({"capabilities": {"total": 215}}))
            code, text = preflight(repo)
            self.assertNotEqual(code, 0, text)
            self.assertIn("CANNOT PROVE ITS AGE", text)


class AuthorityFiles(unittest.TestCase):
    def test_the_bootstrap_stays_thin_and_delegates(self):
        text = BOOTSTRAP.read_text()
        self.assertLess(len(text.splitlines()), 60, "CLAUDE.md is becoming a second doctrine")
        for pointer in ("AGENT_CONTEXT.md", "ACTIVE_WORK.yaml", "preflight"):
            self.assertIn(pointer, text)

    def test_doctrine_is_not_duplicated_across_the_two_files(self):
        """Two substantive instruction files is how they drift apart."""
        context = CONTEXT.read_text()
        self.assertIn("Mission", context)
        self.assertNotIn("Mission", BOOTSTRAP.read_text())

    def test_the_active_task_is_readable_and_singular(self):
        text = ACTIVE.read_text()
        self.assertEqual(len(re.findall(r"(?m)^active:", text)), 1)
        self.assertRegex(text, r"(?m)^active:\n(?:\s+.*\n)*?\s+task:\s+\S+")

    def test_a_task_switch_requires_a_named_condition(self):
        text = ACTIVE.read_text()
        for condition in ("FOUNDER_OVERRIDE", "CURRENT_TASK_COMPLETED",
                          "RELEASE_CONDITION_MET", "VERIFIED_P0_P1_INTERRUPT"):
            self.assertIn(condition, text)
        self.assertRegex(text, r"(?m)^history:")
        self.assertIn("condition:", text)

    def test_the_market_layer_is_parked_not_active(self):
        text = ACTIVE.read_text()
        active_block = text.split("active:", 1)[1].split("\ncompleted:", 1)[0]
        self.assertNotIn("market_hypothesis_layer", active_block)
        self.assertIn("market_hypothesis_layer", text.split("parked:", 1)[1])
        self.assertIn("Market Hypothesis", (ROOT / "PARKING_LOT.md").read_text())

    def test_the_recent_context_rule_is_stated_where_a_session_starts(self):
        self.assertIn("Discovery is not authorisation", BOOTSTRAP.read_text())

    def test_no_volatile_numbers_are_written_into_the_authority_files(self):
        """Counts and SHAs belong in generated state. A number here is a claim about
        the past wearing the present tense."""
        for path in (CONTEXT, ACTIVE):
            text = path.read_text()
            body = "\n".join(l for l in text.splitlines()
                             if "evidence:" not in l and not l.strip().startswith("#"))
            self.assertNotRegex(body, r"\b\d+\s+(tests?|events?|prospects?|invitations?|exposures?)\b",
                                f"{path.name} hard-codes a count")
            self.assertNotRegex(body, r"\b[0-9a-f]{40}\b", f"{path.name} hard-codes a SHA")

    def test_the_dated_gates_are_present_and_dated(self):
        text = ACTIVE.read_text()
        for gate in ("EXP-ACQ-0006", "EXP-ACQ-0003"):
            self.assertIn(gate, text)
        self.assertGreaterEqual(len(re.findall(r"not_before:\s*\d{4}-\d{2}-\d{2}", text)), 3)


class GeneratedState(unittest.TestCase):
    def test_the_state_file_names_its_own_commit_and_time(self):
        runtime = json.loads(STATE.read_text()).get("runtime", {})
        self.assertIn("generated_at", runtime)
        self.assertIn("git_head", runtime)
        self.assertIn("git_dirty", runtime)

    def test_the_snapshot_half_stays_deterministic(self):
        """Volatile values must not leak into the part docs_check compares, or every
        regeneration would read as drift."""
        sys.path.insert(0, str(ROOT / "src"))
        from ai_growth_engineering.snapshot import snapshot
        db = str(ROOT / ".age" / "growth.db")
        if not Path(db).exists():
            self.skipTest("no store")
        first, second = snapshot(db), snapshot(db)
        self.assertEqual(json.dumps(first, sort_keys=True), json.dumps(second, sort_keys=True))
        self.assertNotIn("runtime", first)

    def test_dynamic_counts_come_from_the_store_not_from_prose(self):
        sys.path.insert(0, str(ROOT / "src"))
        from ai_growth_engineering.snapshot import snapshot
        db = str(ROOT / ".age" / "growth.db")
        if not Path(db).exists():
            self.skipTest("no store")
        live = snapshot(db)["store"]
        recorded = json.loads(STATE.read_text())["store"]
        self.assertEqual(live["events"]["log_sha256"], recorded["events"]["log_sha256"])

    def test_generation_does_not_read_any_project_memory(self):
        source = (ROOT / "src" / "ai_growth_engineering" / "snapshot.py").read_text()
        for forbidden in (".claude", "memory", "MEMORY"):
            self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
