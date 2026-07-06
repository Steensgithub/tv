import unittest

from stock_screener_v4 import RealtimeEvaluationEngine


class RealtimeEvaluationEngineTests(unittest.TestCase):
    def test_marks_stale_without_recent_data(self):
        engine = RealtimeEvaluationEngine(stale_after_seconds=1)
        engine.ingest("AAA", 100, 10, timestamp=1)
        cls, _ = engine.evaluate("AAA")
        self.assertEqual(cls, "stale")

    def test_flags_vcp_as_qualified(self):
        engine = RealtimeEvaluationEngine(stale_after_seconds=999999)
        prices = [
            90, 110, 92, 108, 95, 107, 96, 106,
            98, 105, 99, 104, 100, 103, 101, 102,
            100.5, 101.5, 101, 101.8, 101.7, 101.9,
            101.8, 101.95, 101.9, 101.97, 101.95, 101.98,
            101.96, 102,
        ]
        for p in prices:
            engine.ingest("AAA", p, 100)
        cls, discovery = engine.evaluate("AAA")
        self.assertEqual(cls, "qualified")
        self.assertTrue(discovery.vcp)

    def test_near_when_not_discovery_but_supported(self):
        engine = RealtimeEvaluationEngine(stale_after_seconds=999999)
        for price in [100, 100.2, 100.3, 100.25, 100.35, 100.4, 100.45, 100.5, 100.55, 100.6]:
            engine.ingest("AAA", price, 100)
        cls, discovery = engine.evaluate("AAA")
        self.assertEqual(cls, "near")
        self.assertFalse(discovery.vcp)
        self.assertFalse(discovery.gap_go)


if __name__ == "__main__":
    unittest.main()
