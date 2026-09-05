"""
TraceFace — Unit Tests for Search Normalization & Deduplication
===============================================================
Tests deterministic URL canonicalization, deduplication hierarchy, and
multi-provider agreement aggregation.
"""
import unittest
from traceface.search.models import SearchMatch
from traceface.search.normalize import deduplicate_matches, normalize_url


class TestSearchNormalization(unittest.TestCase):

    def test_normalize_url(self):
        raw_url = "https://WWW.Instagram.com/p/Post123/?utm_source=feed&ref=banner&b=2&a=1#section"
        expected = "https://www.instagram.com/p/Post123/?a=1&b=2"
        normalized = normalize_url(raw_url)
        self.assertEqual(normalized, expected)

    def test_deduplicate_matches_provider_agreement(self):
        matches = [
            SearchMatch(
                url="https://x.com/profile/status/12345?utm_source=twitter",
                thumbnail_url="https://pbs.twimg.com/media/pic.jpg",
                similarity=0.75,
                source="yandex",
                person_name="John Doe",
            ),
            SearchMatch(
                url="https://x.com/profile/status/12345?fbclid=xyz",
                thumbnail_url="https://pbs.twimg.com/media/pic.jpg",
                similarity=0.82,
                source="google",
                person_name="John Doe",
            ),
            SearchMatch(
                url="https://example.com/other-page",
                thumbnail_url="https://example.com/other.jpg",
                similarity=0.50,
                source="bing",
            ),
        ]

        candidates = deduplicate_matches(matches)

        # 3 raw matches -> 2 unique candidates
        self.assertEqual(len(candidates), 2)

        # First candidate should have both 'google' and 'yandex' providers
        c1 = candidates[0]
        self.assertEqual(c1.canonical_url, "https://x.com/profile/status/12345")
        self.assertIn("google", c1.providers)
        self.assertIn("yandex", c1.providers)
        self.assertEqual(len(c1.providers), 2)
        self.assertEqual(c1.candidate_id, "candidate_01")
        self.assertEqual(c1.person_name, "John Doe")

        c2 = candidates[1]
        self.assertEqual(c2.canonical_url, "https://example.com/other-page")
        self.assertEqual(c2.providers, ["bing"])
        self.assertEqual(c2.candidate_id, "candidate_02")


if __name__ == "__main__":
    unittest.main()
