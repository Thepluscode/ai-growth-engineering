import unittest

from ai_growth_engineering.scoring import CongruenceScore, OutreachQuality


class ScoringTests(unittest.TestCase):
    def test_outreach_send_threshold(self):
        score = OutreachQuality(5, 4, 4, 4, 4, 4)
        self.assertEqual(score.total, 25)
        self.assertEqual(score.decision, "SEND")

    def test_outreach_do_not_send(self):
        score = OutreachQuality(2, 2, 2, 2, 2, 2)
        self.assertEqual(score.decision, "DO_NOT_SEND")

    def test_congruence_gate(self):
        score = CongruenceScore(4, 4, 4, 4, 4, 4)
        self.assertEqual(score.total, 24)
        self.assertEqual(score.decision, "ELIGIBLE_FOR_TEST")


if __name__ == "__main__":
    unittest.main()
