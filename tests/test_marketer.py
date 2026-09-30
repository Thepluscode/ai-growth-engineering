"""The marketer against a scripted model and a scripted web. Nothing here reaches the network.
Each case builds exactly the candidates and pages it needs; expected counts are hard-coded."""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from ai_growth_engineering import registries
from ai_growth_engineering.marketer import (LLMResult, MarketerError, candidates_of, fetch_page, gmail_payloads,
                                            import_candidates, page_text, run,
                                            runs)
from ai_growth_engineering.outbound_workbench import approve_draft, get_draft
from ai_growth_engineering.storage import connect, init_db

TEAM = "https://acme.test/team"
NEWS = "https://acme.test/news"
QUOTE = "We now settle payouts across three payment providers"


def candidate(company="Acme", name="Alex Example", email="alex@acme.test", **over):
    c = {"company": company, "website": "https://acme.test", "person_name": name, "role": "Head of Payments",
         "person_source_url": TEAM, "evidence_quote": QUOTE, "evidence_url": NEWS, "email": email,
         "email_source_url": TEAM, "linkedin_url": ""}
    return {**c, **over}


DRAFT = {"subject": "Payouts across three providers", "observation": "Acme settles payouts across three providers.",
         "economic_hypothesis": "Reconciling three providers by hand likely hides delayed or duplicated payouts.",
         "cta": "Want the one-page diagnostic outline?", "metric": "unreconciled payouts"}


class FakeLLM:
    def __init__(self, research, draft=DRAFT, fail=None):
        self.research, self.draft, self.fail, self.calls = research, draft, fail, []

    def __call__(self, prompt, max_searches):
        self.calls.append(max_searches)
        if self.fail:
            raise self.fail
        if max_searches:
            text = self.research if isinstance(self.research, str) else json.dumps(self.research)
            return LLMResult(text, 1000, 500, 4)
        return LLMResult(json.dumps(self.draft), 300, 150, 0)


PAGES = {TEAM: "<html><h2>Alex Example</h2><p>Head of Payments</p><a>alex@acme.test</a>"
               "<a href='https://uk.linkedin.com/in/example-alex'>in</a></html>",
         NEWS: f"<p>News: {QUOTE} this year.</p>"}


def fetch(pages=PAGES):
    return lambda url: pages.get(url, "")


class Case(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.db = str(Path(self.tmp.name) / "g.db")
        init_db(self.db)
        registries.add(self.db, "offers", {"offer_id": "OFF-X", "buyer": "Head of Payments", "problem": "payouts go missing",
                                           "outcome": "a payment reliability diagnostic"})
        registries.add(self.db, "markets", {"market_id": "MKT-X", "hypothesis": "multi-provider firms pay for a diagnostic",
                                            "buyer": "Head of Payments", "offer_id": "OFF-X",
                                            "forbidden_claims": "guaranteed savings;enforceable since"})
        registries.add(self.db, "market_experiments", {
            "link_id": "L1", "market_id": "MKT-X", "experiment_id": "EXP-X", "layer": "DEMAND",
            "protocol": "named-buyer-message-v1", "exposure_event": "message_sent", "positive_event": "reply_meaningful"})

    def go(self, research, **kw):
        llm = kw.pop("llm", None) or FakeLLM(research, **{k: kw.pop(k) for k in ("draft", "fail") if k in kw})
        return run(self.db, "MKT-X", llm=llm, fetch=kw.pop("fetch", fetch()), **kw), llm


class HappyPath(Case):
    def test_verified_candidates_become_tagged_drafts_awaiting_approval(self):
        result, _ = self.go([candidate(), candidate(company="Beta")], count=2)
        self.assertEqual((result["proposed"], result["drafted"], result["error"]), (2, 2, ""))
        draft = get_draft(self.db, result["draft_ids"][0])
        self.assertEqual((draft["status"], draft["experiment_id"], draft["recipient_class"], draft["channel"]),
                         ("pending_approval", "EXP-X", "named_buyer", "email"))
        self.assertTrue(draft["message"].startswith("Hi Alex,\n\n"))
        self.assertEqual(draft["subject"], "Payouts across three providers")

    def test_the_run_is_logged_with_its_cost(self):
        result, _ = self.go([candidate()], count=1)
        row = runs(self.db)[0]
        self.assertEqual((row["drafted"], row["input_tokens"], row["output_tokens"], row["web_searches"]),
                         (1, 1300, 650, 4))
        self.assertEqual(row["id"], result["run_id"])

    def test_dry_run_writes_nothing_but_the_log(self):
        result, _ = self.go([candidate()], count=1, dry_run=True)
        self.assertEqual((result["drafted"], len(result["previews"])), (0, 1))
        with connect(self.db) as con:
            self.assertEqual(con.execute("SELECT count(*) FROM prospects").fetchone()[0], 0)
            self.assertEqual(con.execute("SELECT count(*) FROM outbound_drafts").fetchone()[0], 0)
        self.assertEqual(len(runs(self.db)), 1)


class Verification(Case):
    def reason(self, research, pages=PAGES):
        return self.go(research, count=1, fetch=fetch(pages))[0]["rejections"]

    def test_a_name_that_is_not_on_its_source_page_is_rejected(self):
        self.assertEqual(self.reason([candidate(name="Invented Person")]), {"name_not_on_source": 1})

    def test_a_quote_that_is_not_verbatim_on_its_page_is_rejected(self):
        self.assertEqual(self.reason([candidate(evidence_quote="We settle payouts across four payment providers")]),
                         {"quote_not_on_source": 1})

    def test_a_quote_hidden_in_a_script_does_not_count(self):
        pages = {**PAGES, NEWS: f"<script>var s = '{QUOTE}';</script><p>nothing here</p>"}
        self.assertEqual(self.reason([candidate()], pages), {"quote_not_on_source": 1})

    def test_an_unreachable_source_is_rejected(self):
        self.assertEqual(self.reason([candidate()], {}), {"source_unreachable": 1})

    def test_a_guessed_email_is_dropped_and_linkedin_used_when_verified(self):
        result, _ = self.go([candidate(email="a.example@acme.test",
                                       linkedin_url="https://uk.linkedin.com/in/example-alex")], count=1)
        self.assertEqual(result["rejections"], {"email_unverified_dropped": 1})
        self.assertEqual(get_draft(self.db, result["draft_ids"][0])["channel"], "linkedin")

    def test_a_verified_person_without_a_route_is_queued_for_manual_lookup_not_guessed(self):
        result, _ = self.go([candidate(email="guess@acme.test")], count=1)
        self.assertEqual(result["rejections"], {"email_unverified_dropped": 1, "route_manual_lookup": 1})
        draft = get_draft(self.db, result["draft_ids"][0])
        self.assertEqual(draft["channel"], "linkedin")
        self.assertEqual(draft["recipient_identity"], "Alex Example at Acme (find on LinkedIn by name)")

    def test_an_existing_prospect_is_not_researched_twice(self):
        with connect(self.db) as con:
            con.execute("INSERT INTO prospects(company) VALUES ('Acme')")
        self.assertEqual(self.reason([candidate()]), {"duplicate_company": 1})

    def test_a_suppressed_address_is_rejected(self):
        with connect(self.db) as con:
            con.execute("INSERT INTO suppression(identity, reason) VALUES ('alex@acme.test', 'opted out')")
        self.assertEqual(self.reason([candidate()]), {"suppressed": 1})

    def test_a_draft_with_a_forbidden_claim_is_rejected(self):
        bad = {**DRAFT, "economic_hypothesis": "This comes with guaranteed savings for any payments team."}
        result, _ = self.go([candidate()], count=1, draft=bad)
        self.assertEqual((result["drafted"], result["rejections"]), (0, {"forbidden_claim": 1}))

    def test_a_draft_that_breaks_the_workbench_rules_is_rejected(self):
        result, _ = self.go([candidate()], count=1, draft={**DRAFT, "cta": "Can we book a call next week?"})
        self.assertEqual(result["drafted"], 0)
        self.assertEqual(sum(result["rejections"].values()), 1)


class Failure(Case):
    def test_unparseable_research_is_recorded_not_raised(self):
        result, _ = self.go("I could not find anyone.", count=1)
        self.assertTrue(result["error"].startswith("unparseable_output"))
        self.assertTrue(runs(self.db)[0]["error"].startswith("unparseable_output"))

    def test_a_model_failure_is_recorded_not_swallowed(self):
        result, _ = self.go([], count=1, fail=TimeoutError("model timed out"))
        self.assertEqual(result["error"], "TimeoutError: model timed out")
        self.assertEqual(runs(self.db)[0]["error"], "TimeoutError: model timed out")

    def test_cost_is_capped(self):
        _, llm = self.go([], count=100)
        self.assertEqual(llm.calls[0], 40)
        _, llm = self.go([], count=2)
        self.assertEqual(llm.calls[0], 6)

    def test_a_market_without_an_offer_is_refused(self):
        registries.add(self.db, "markets", {"market_id": "MKT-NO-OFFER", "hypothesis": "h"})
        registries.add(self.db, "market_experiments", {
            "link_id": "L2", "market_id": "MKT-NO-OFFER", "experiment_id": "EXP-Y", "layer": "DEMAND",
            "protocol": "p", "exposure_event": "message_sent", "positive_event": "reply_meaningful"})
        with self.assertRaises(MarketerError) as ctx:
            run(self.db, "MKT-NO-OFFER", llm=FakeLLM([]), fetch=fetch())
        self.assertEqual(ctx.exception.code, "no_offer")


class ImportAndLog(Case):
    def test_imported_candidates_meet_the_same_bar_and_spend_no_searches(self):
        llm = FakeLLM([])
        result = import_candidates(self.db, "MKT-X", [candidate(), candidate(company="Beta", name="Invented Person")],
                                   llm=llm, fetch=fetch())
        self.assertEqual((result["drafted"], result["rejections"], result["web_searches"]),
                         (1, {"name_not_on_source": 1}, 0))
        self.assertEqual(llm.calls, [0], "import makes one draft call and no research call")

    def test_every_candidate_is_logged_with_its_outcome(self):
        result, _ = self.go([candidate(), candidate(company="Beta", name="Invented Person")], count=2)
        log = candidates_of(self.db, result["run_id"])
        self.assertEqual([(r["company"], r["outcome"]) for r in log],
                         [("Acme", "drafted"), ("Beta", "name_not_on_source")])
        self.assertEqual(log[0]["draft_id"], result["draft_ids"][0])
        self.assertEqual(log[1]["person_source_url"], TEAM)

    def test_a_malformed_import_is_refused(self):
        with self.assertRaises(MarketerError):
            import_candidates(self.db, "MKT-X", {"company": "Acme"}, llm=FakeLLM([]), fetch=fetch())


class Adapters(Case):
    def test_fetch_refuses_private_and_loopback_addresses(self):
        """Every address here would answer, so only the guard can make the result empty."""
        from unittest import mock

        class Page:
            headers = mock.Mock(get_content_charset=lambda: "utf-8")

            def read(self, n):
                return b"secret internal page"

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

        with mock.patch("urllib.request.urlopen", return_value=Page()):
            self.assertEqual(fetch_page("http://93.184.215.14/"), "secret internal page")   # positive twin
            for url in ("http://127.0.0.1/", "http://10.0.0.1/", "http://169.254.169.254/latest",
                        "file:///etc/passwd"):
                self.assertEqual(fetch_page(url), "", url)

    def test_page_text_is_visible_text_only(self):
        self.assertEqual(page_text("<p>A&amp;B</p><style>x{}</style>\n  <b>C</b>"), "a&b c")

    def test_only_approved_email_drafts_go_to_gmail(self):
        result, _ = self.go([candidate(), candidate(company="Beta")], count=2)
        approve_draft(self.db, result["draft_ids"][1])
        payloads = gmail_payloads(self.db)
        self.assertEqual([p["draft_id"] for p in payloads], [result["draft_ids"][1]])
        self.assertEqual(payloads[0]["to"], "alex@acme.test")


if __name__ == "__main__":
    unittest.main()
