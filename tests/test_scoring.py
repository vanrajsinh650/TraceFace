"""
TraceFace — Unit Tests for Multi-Signal Evidence Scoring
========================================================
Tests explainable confidence calculation, weighting integrity, and breakdown reports.
"""
import unittest
from traceface.evidence.scoring import calculate_evidence_confidence


class TestScoring(unittest.TestCase):

    def test_high_confidence_match(self):
        score = calculate_evidence_confidence(
            face_similarity=0.78,
            threshold=0.35,
            margin=0.45,
            candidate_faces_checked=2,
            providers=["yandex", "google", "bing"],
            matched_url="https://instagram.com/p/abc123xyz",
            image_width=600,
            image_height=600,
        )

        self.assertGreaterEqual(score.total_score, 80.0)
        self.assertEqual(score.rating, "VERY_STRONG")
        self.assertEqual(len(score.components), 5)

        # Check that each signal component is present and within bounds
        for comp in score.components:
            self.assertGreaterEqual(comp.points, 0.0)
            self.assertLessEqual(comp.points, comp.max_points)
            self.assertIsNotNone(comp.assessment)
            self.assertIsNotNone(comp.raw_value)

    def test_sub_threshold_match(self):
        score = calculate_evidence_confidence(
            face_similarity=0.25,  # Below threshold
            threshold=0.35,
            margin=0.05,
            candidate_faces_checked=1,
            providers=["yandex"],
            matched_url="https://example.com/unknown",
            image_width=100,
            image_height=100,
        )

        self.assertLess(score.total_score, 50.0)
        self.assertIn(score.rating, ("LOW", "MODERATE"))

    def test_provider_agreement_boost(self):
        score_single = calculate_evidence_confidence(
            face_similarity=0.60,
            threshold=0.35,
            providers=["yandex"],
            matched_url="https://example.com/item",
        )
        score_multi = calculate_evidence_confidence(
            face_similarity=0.60,
            threshold=0.35,
            providers=["yandex", "google", "bing"],
            matched_url="https://example.com/item",
        )

        # Multi-provider agreement must give higher overall confidence
        self.assertGreater(score_multi.total_score, score_single.total_score)

        prov_comp_single = next(c for c in score_single.components if c.name == "provider_agreement")
        prov_comp_multi = next(c for c in score_multi.components if c.name == "provider_agreement")
        self.assertGreater(prov_comp_multi.points, prov_comp_single.points)


if __name__ == "__main__":
    unittest.main()
