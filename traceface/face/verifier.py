"""
TraceFace — Face Verifier
==========================
Compares a query face embedding against all faces detected in a candidate image.

Critical rule: NEVER compare only candidate_faces[0].
Always compare against ALL faces and take the best score.

Source: eye_of_web/src/lib/similarity_utils.py (MIT — Mehmet Yüksel Şekeroğlu)
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import numpy as np

from traceface.face.detector import DetectedFace, DetectionResult, FaceDetector, cosine_similarity


@dataclass
class VerificationResult:
    """Result of comparing a query face against a candidate image."""
    best_score: float               # Cosine similarity of closest match
    runner_up_score: Optional[float]  # Second closest (if ≥2 faces in candidate)
    margin: Optional[float]         # best_score - runner_up_score
    candidate_faces_checked: int    # Total faces found in candidate
    matched_face_index: int         # Index (0-based) of best matching face
    passed_threshold: bool          # True if best_score >= threshold
    threshold_used: float
    error: Optional[str] = None


# Default cosine similarity threshold for InsightFace buffalo_l
# INFERRED from typical ArcFace operational ranges — validate experimentally.
DEFAULT_THRESHOLD = 0.35


class FaceVerifier:
    """
    Verifies a query face against a candidate image.

    Follows the rule: detect ALL faces in candidate, compare query against each,
    report best_score, runner_up_score, and margin.

    Usage:
        verifier = FaceVerifier(detector)
        result = verifier.verify(query_embedding, candidate_image_bytes)
        if result.passed_threshold:
            print(f"MATCH — score: {result.best_score:.3f}")
    """

    def __init__(
        self,
        detector: FaceDetector | None = None,
        threshold: float = DEFAULT_THRESHOLD,
    ) -> None:
        self._detector = detector or FaceDetector()
        self._threshold = threshold

    @property
    def threshold(self) -> float:
        return self._threshold

    def verify(
        self,
        query_embedding: list[float],
        candidate_image_bytes: bytes,
    ) -> VerificationResult:
        """
        Compare a query embedding against all faces in a candidate image.

        Steps:
        1. Detect ALL faces in the candidate image
        2. Compute cosine similarity between query and each candidate face
        3. Return best_score, runner_up_score, and margin

        Args:
            query_embedding: 512-dim ArcFace embedding of the query face
            candidate_image_bytes: Raw bytes of the candidate image

        Returns:
            VerificationResult
        """
        if not query_embedding:
            return VerificationResult(
                best_score=0.0,
                runner_up_score=None,
                margin=None,
                candidate_faces_checked=0,
                matched_face_index=-1,
                passed_threshold=False,
                threshold_used=self._threshold,
                error="Query embedding is empty",
            )

        # Detect faces in candidate image
        detection: DetectionResult = self._detector.detect(candidate_image_bytes)

        if not detection.success:
            return VerificationResult(
                best_score=0.0,
                runner_up_score=None,
                margin=None,
                candidate_faces_checked=0,
                matched_face_index=-1,
                passed_threshold=False,
                threshold_used=self._threshold,
                error=f"Candidate face detection failed: {detection.error}",
            )

        if not detection.faces:
            return VerificationResult(
                best_score=0.0,
                runner_up_score=None,
                margin=None,
                candidate_faces_checked=0,
                matched_face_index=-1,
                passed_threshold=False,
                threshold_used=self._threshold,
                error="No faces detected in candidate image",
            )

        # Compare query against ALL detected faces
        scores: list[tuple[int, float]] = []  # (index, score)
        query_arr = np.array(query_embedding, dtype=np.float32)

        for i, face in enumerate(detection.faces):
            if not face.embedding:
                continue
            score = cosine_similarity(query_arr, face.embedding)
            scores.append((i, score))

        if not scores:
            return VerificationResult(
                best_score=0.0,
                runner_up_score=None,
                margin=None,
                candidate_faces_checked=len(detection.faces),
                matched_face_index=-1,
                passed_threshold=False,
                threshold_used=self._threshold,
                error="No embeddings generated for candidate faces",
            )

        # Sort by score descending
        scores.sort(key=lambda x: x[1], reverse=True)

        best_idx, best_score = scores[0]
        runner_up_score: Optional[float] = None
        margin: Optional[float] = None

        if len(scores) >= 2:
            runner_up_score = scores[1][1]
            margin = best_score - runner_up_score

        return VerificationResult(
            best_score=best_score,
            runner_up_score=runner_up_score,
            margin=margin,
            candidate_faces_checked=len(detection.faces),
            matched_face_index=best_idx,
            passed_threshold=best_score >= self._threshold,
            threshold_used=self._threshold,
        )

    def verify_from_url(
        self,
        query_embedding: list[float],
        candidate_url: str,
        timeout: int = 15,
    ) -> VerificationResult:
        """
        Download a candidate image from a URL and verify the face.

        Args:
            query_embedding: 512-dim ArcFace embedding of the query face
            candidate_url: URL of the candidate image to download
            timeout: Request timeout in seconds

        Returns:
            VerificationResult
        """
        try:
            import httpx
            with httpx.Client(timeout=timeout, follow_redirects=True) as client:
                resp = client.get(
                    candidate_url,
                    headers={"User-Agent": "TraceFace/1.0 (research)"},
                )
                resp.raise_for_status()
                image_bytes = resp.content
        except Exception as e:
            return VerificationResult(
                best_score=0.0,
                runner_up_score=None,
                margin=None,
                candidate_faces_checked=0,
                matched_face_index=-1,
                passed_threshold=False,
                threshold_used=self._threshold,
                error=f"Failed to download candidate image from {candidate_url}: {e}",
            )

        return self.verify(query_embedding, image_bytes)
