import unittest

from ai_growth_engineering.teardown import TeardownPacket


class TeardownTests(unittest.TestCase):
    def test_packet_separates_fact_and_inference(self):
        text = TeardownPacket("Acme", "Observed CTA is generic", "Specific CTA may improve conversion", "qualified_booking_rate").markdown()
        self.assertIn("Observed CTA is generic", text)
        self.assertIn("Inference", text)
        self.assertIn("qualified_booking_rate", text)


if __name__ == "__main__":
    unittest.main()
