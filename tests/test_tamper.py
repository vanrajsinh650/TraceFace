"""
TraceFace — Unit Tests for Cryptographic Verification & Tamper Detection
========================================================================
Tests that pristine evidence produces VERIFIED and modified evidence produces TAMPERED.
"""
import io
import tempfile
import unittest
from pathlib import Path
from PIL import Image

from traceface.blockchain.verifier import reverify_package, run_tamper_demo
from traceface.evidence.graph import build_investigation_graph
from traceface.evidence.models import CandidateEvidenceItem, MatchedCandidateEvidence
from traceface.evidence.package import (
    build_evidence_package,
    load_evidence_package,
    save_evidence_package,
)
from traceface.evidence.scoring import calculate_evidence_confidence


def _build_dummy_evidence_package() -> tuple:
    # 1x1 test image
    img = Image.new("RGB", (100, 100), color="white")
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    img_bytes = buf.getvalue()

    cand1 = CandidateEvidenceItem(
        candidate_id="candidate_01",
        canonical_url="https://example.com/item1",
        source_domain="example.com",
        image_url="https://example.com/item1.jpg",
        providers=["yandex"],
        face_similarity_score=0.745,
        runner_up_score=0.20,
        margin=0.545,
        candidate_faces_checked=2,
        verification_status="MATCH",
        evidence_confidence=82.0,
    )

    cand2 = CandidateEvidenceItem(
        candidate_id="candidate_02",
        canonical_url="https://example.com/item2",
        source_domain="example.com",
        image_url="https://example.com/item2.jpg",
        providers=["google"],
        face_similarity_score=0.22,
        verification_status="NO_MATCH",
        evidence_confidence=40.0,
    )

    matched = MatchedCandidateEvidence(
        matched_candidate_id="candidate_01",
        matched_source_url="https://example.com/item1",
        matched_image_url="https://example.com/item1.jpg",
        matched_image_sha256="1" * 64,
        matched_image_perceptual_hash="abcdef0123456789",
        matched_face_similarity=0.745,
        matched_verification_status="MATCH",
        source_domain="example.com",
        providers=["yandex"],
        evidence_confidence=82.0,
    )

    score = calculate_evidence_confidence(
        face_similarity=0.745,
        threshold=0.35,
        margin=0.545,
        candidate_faces_checked=2,
        providers=["yandex"],
        matched_url="https://example.com/item1",
    )

    graph = build_investigation_graph(
        investigation_id="inv_test_01",
        query_image_sha="2" * 64,
        query_face_bbox=(10, 10, 80, 80),
        query_face_conf=0.99,
        providers_run={"yandex": {"status": "success", "latency_ms": 100, "matches_count": 2}},
        candidates_data=[cand1.to_canonical_dict(), cand2.to_canonical_dict()],
        matched_candidate_id="candidate_01",
        verification_data={"best_score": 0.745, "threshold": 0.35, "passed": True},
        evidence_package_id="inv_test_01",
    )

    pkg = build_evidence_package(
        investigation_id="inv_test_01",
        query_image_bytes=img_bytes,
        query_face_bbox=(10, 10, 80, 80),
        query_face_confidence=0.99,
        provider_runs={"yandex": {"status": "success", "latency_ms": 100, "matches_count": 2}},
        candidate_items=[cand1, cand2],
        matched_candidate=matched,
        confidence_score=score,
        evidence_graph=graph,
    )

    return pkg, img_bytes


class TestTamper(unittest.TestCase):

    def test_pristine_evidence_reverification(self):
        pkg, _ = _build_dummy_evidence_package()
        report = reverify_package(pkg, check_blockchain=False)

        self.assertTrue(report.is_valid)
        self.assertEqual(report.status, "VERIFIED")
        self.assertTrue(report.root_match)
        self.assertTrue(report.sha256_match)
        self.assertTrue(report.inclusion_proof_valid)
        self.assertEqual(len(report.tamper_details), 0)

    def test_tamper_detection_in_package(self):
        pkg, _ = _build_dummy_evidence_package()

        # Tamper with candidate score
        pkg.candidates[0].face_similarity_score = 0.999999
        report = reverify_package(pkg, check_blockchain=False)

        self.assertFalse(report.is_valid)
        self.assertEqual(report.status, "TAMPERED")
        self.assertFalse(report.root_match)
        self.assertGreater(len(report.tamper_details), 0)

    def test_tamper_demo_workflow(self):
        pkg, _ = _build_dummy_evidence_package()

        with tempfile.TemporaryDirectory() as tmpdir:
            file_path = save_evidence_package(pkg, output_dir=tmpdir)

            baseline, tampered = run_tamper_demo(file_path, tamper_field="similarity", check_blockchain=False)

            self.assertTrue(baseline.is_valid)
            self.assertEqual(baseline.status, "VERIFIED")

            self.assertFalse(tampered.is_valid)
            self.assertEqual(tampered.status, "TAMPERED")
            self.assertFalse(tampered.root_match)

            # Verify disk file remained untouched
            reloaded_pkg, _ = load_evidence_package(file_path)
            re_check = reverify_package(reloaded_pkg, check_blockchain=False)
            self.assertTrue(re_check.is_valid)


if __name__ == "__main__":
    unittest.main()
