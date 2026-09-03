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
