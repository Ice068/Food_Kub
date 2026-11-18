"""Catalog safety and availability behavior independent of a live backend."""
import random
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "front_py"))
from app.services.discovery_service import DiscoveryService


class DiscoveryTests(unittest.TestCase):
    def test_unavailable_food_can_never_win_the_wheel(self):
        catalog = [{"id": 1, "available": False}, {"id": 2, "available": True}]
        for seed in range(10):
            result = DiscoveryService.build_wheel(catalog, spin=True, rng=random.Random(seed))
            self.assertEqual(result["winner"]["id"], 2)
            self.assertEqual(result["pool_count"], 1)
        self.assertIsNone(DiscoveryService.build_wheel(catalog[:1], spin=True)["winner"])

    def test_recommendations_skip_unavailable_or_missing_dishes(self):
        catalog = [{"id": 1, "available": False}, {"id": 7, "available": True}]
        self.assertEqual(DiscoveryService.recommendations(catalog), [catalog[1]])

    def test_malformed_or_unsafe_image_urls_do_not_break_the_catalog(self):
        for value in ("http://[invalid", "javascript:alert(1)", "../private", "//example.com/food.jpg"):
            self.assertEqual(DiscoveryService.image_url(value), "")
        self.assertEqual(DiscoveryService.image_url("pad_kra_pao.jpg"), "/static/images/pad_kra_pao.jpg")


if __name__ == "__main__":
    unittest.main()
