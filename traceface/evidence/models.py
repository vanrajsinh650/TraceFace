"""
TraceFace — Evidence Data Models (Schema v2.0)
==============================================
Typed models representing the complete cryptographic evidence ledger.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class CandidateEvidenceItem:
    """Detailed evidence unit for an individual candidate in the investigation."""
    candidate_id: str
    canonical_url: str
    source_domain: str
    image_url: str
    providers: list[str]
    image_sha256: Optional[str] = None
    perceptual_hash: Optional[str] = None
    perceptual_algorithm: Optional[str] = None
    face_similarity_score: Optional[float] = None
    runner_up_score: Optional[float] = None
    margin: Optional[float] = None
    candidate_faces_checked: int = 0
    verification_status: str = "UNCHECKED"    # "MATCH", "NO_MATCH", "UNCHECKED", "DOWNLOAD_FAILED"
    evidence_confidence: Optional[float] = None
    title: Optional[str] = None
    person_name: Optional[str] = None

    def to_canonical_dict(self) -> dict[str, Any]:
        d = {
            "candidate_id": self.candidate_id,
            "canonical_url": self.canonical_url,
            "candidate_faces_checked": self.candidate_faces_checked,
            "evidence_confidence": round(self.evidence_confidence, 2) if self.evidence_confidence is not None else None,
            "face_similarity_score": round(self.face_similarity_score, 6) if self.face_similarity_score is not None else None,
            "image_sha256": self.image_sha256,
            "image_url": self.image_url,
            "margin": round(self.margin, 6) if self.margin is not None else None,
            "perceptual_algorithm": self.perceptual_algorithm,
            "perceptual_hash": self.perceptual_hash,
            "person_name": self.person_name,
            "providers": sorted(self.providers),
            "runner_up_score": round(self.runner_up_score, 6) if self.runner_up_score is not None else None,
            "source_domain": self.source_domain,
            "title": self.title,
            "verification_status": self.verification_status,
        }
        return d


@dataclass
class MatchedCandidateEvidence:
    """Explicitly identified matched social media / web post (Hackathon Feature 9)."""
    matched_candidate_id: str
    matched_source_url: str
    matched_image_url: str
    matched_image_sha256: str
    matched_image_perceptual_hash: Optional[str]
    matched_face_similarity: float
    matched_verification_status: str
    source_domain: str
    providers: list[str]
    evidence_confidence: float
    person_name: Optional[str] = None
    leaf_hash: str = ""

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "evidence_confidence": round(self.evidence_confidence, 2),
            "leaf_hash": self.leaf_hash,
            "matched_candidate_id": self.matched_candidate_id,
            "matched_face_similarity": round(self.matched_face_similarity, 6),
            "matched_image_perceptual_hash": self.matched_image_perceptual_hash,
            "matched_image_sha256": self.matched_image_sha256,
            "matched_image_url": self.matched_image_url,
            "matched_source_url": self.matched_source_url,
            "matched_verification_status": self.matched_verification_status,
            "person_name": self.person_name,
            "providers": sorted(self.providers),
            "source_domain": self.source_domain,
        }


@dataclass
class QueryEvidenceInfo:
    """Query image and face detection cryptographic commitment."""
    query_image_sha256: str
    query_perceptual_hash: Optional[str]
    query_face_bbox: list[int]
    query_face_confidence: float
    model_name: str
    embedding_dimension: int = 512

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "embedding_dimension": self.embedding_dimension,
            "model_name": self.model_name,
            "query_face_bbox": self.query_face_bbox,
            "query_face_confidence": round(self.query_face_confidence, 6),
            "query_image_sha256": self.query_image_sha256,
            "query_perceptual_hash": self.query_perceptual_hash,
        }
