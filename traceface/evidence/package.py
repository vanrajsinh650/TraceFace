"""
TraceFace — Evidence Package & SHA-256 Hashing
================================================
Creates a deterministic, canonical evidence package from a verified match.
Computes SHA-256 of the canonical representation.

Canonical form: json.dumps(evidence_dict, sort_keys=True, separators=(',', ':'))
This ensures the same evidence always produces the same hash.

IMPORTANT: Do NOT use raw face embeddings or biometric data in the evidence package.
           Only metadata, URLs, scores, and timestamps.
"""
from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


@dataclass
class EvidencePackage:
    """
    Deterministic evidence package for a verified face match.

    All fields are used in the canonical hash. Field order is irrelevant —
    json.dumps(sort_keys=True) produces a canonical ordering.

    NEVER include: raw face embeddings, private keys, API keys.
    """
    # Query
    query_image_sha256: str          # SHA-256 of the original input image bytes

    # Match
    matched_url: str                 # URL of the matched page/post
    matched_image_url: str           # URL of the matched image (may differ from page URL)
    source_domain: str               # e.g., "instagram.com"
    search_provider: str             # e.g., "pimeyes", "google", "yandex"

    # Face verification
    face_similarity_score: float     # Cosine similarity (0.0–1.0)
    candidate_faces_checked: int     # Number of faces checked in candidate image
    similarity_threshold: float      # Threshold used for pass/fail

    # Model
    model_name: str                  # e.g., "buffalo_l" (InsightFace)

    # Timestamp
    timestamp_utc: str               # ISO 8601 UTC, e.g., "2026-09-03T10:54:38Z"

    # Optional metadata
    person_name: Optional[str] = None
    runner_up_score: Optional[float] = None
    margin: Optional[float] = None

    def to_canonical_dict(self) -> dict:
        """
        Return the canonical dict used for hashing.
        All keys are included. None values are included as null.
        """
        d = asdict(self)
        # Round floats to 6 decimal places for canonical representation
        for key in ("face_similarity_score", "similarity_threshold", "runner_up_score", "margin"):
            if d[key] is not None:
                d[key] = round(float(d[key]), 6)
        return d

    def canonical_json(self) -> str:
        """
        Deterministic JSON representation.
        sort_keys=True ensures key order is alphabetical regardless of insertion order.
        separators=(',', ':') removes whitespace for minimal canonical form.
        """
        return json.dumps(self.to_canonical_dict(), sort_keys=True, separators=(",", ":"))

    def sha256(self) -> str:
        """
        Compute SHA-256 of the canonical JSON representation.
        Returns hex digest (64 characters).
        """
        canonical_bytes = self.canonical_json().encode("utf-8")
        return hashlib.sha256(canonical_bytes).hexdigest()


def hash_image_bytes(image_bytes: bytes) -> str:
    """Compute SHA-256 of raw image bytes. Used for query_image_sha256."""
    return hashlib.sha256(image_bytes).hexdigest()


def create_evidence_package(
    query_image_bytes: bytes,
    matched_url: str,
    matched_image_url: str,
    search_provider: str,
    face_similarity_score: float,
    candidate_faces_checked: int,
    similarity_threshold: float,
    model_name: str = "buffalo_l",
    person_name: Optional[str] = None,
    runner_up_score: Optional[float] = None,
    margin: Optional[float] = None,
) -> EvidencePackage:
    """
    Create a deterministic evidence package from a verified match.

    Args:
        query_image_bytes: Raw bytes of the input query image
        matched_url: URL of the matched web page
        matched_image_url: URL of the matched image (to download for verification)
        search_provider: Which search engine found this match
        face_similarity_score: Best cosine similarity from face verification
        candidate_faces_checked: How many faces were detected in candidate
        similarity_threshold: The threshold used to determine pass/fail
        model_name: InsightFace model used
        person_name: Best-guess name from search results (optional)
        runner_up_score: Second-best similarity score (optional)
        margin: best_score - runner_up_score (optional)

    Returns:
        EvidencePackage (call .sha256() to get the blockchain commitment)
    """
    from urllib.parse import urlparse

    source_domain = urlparse(matched_url).netloc.lower()
    query_sha256 = hash_image_bytes(query_image_bytes)
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    return EvidencePackage(
        query_image_sha256=query_sha256,
        matched_url=matched_url,
        matched_image_url=matched_image_url,
        source_domain=source_domain,
        search_provider=search_provider,
        face_similarity_score=face_similarity_score,
        candidate_faces_checked=candidate_faces_checked,
        similarity_threshold=similarity_threshold,
        model_name=model_name,
        timestamp_utc=timestamp,
        person_name=person_name,
        runner_up_score=runner_up_score,
        margin=margin,
    )


def save_evidence_package(
    package: EvidencePackage,
    evidence_hash: str,
    output_dir: Path | str = "results",
) -> Path:
    """
    Save the evidence package as a JSON file.

    The file is saved to: results/evidence_<hash[:12]>.json
    results/ is gitignored.

    Returns:
        Path to the saved file.
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    filename = f"evidence_{evidence_hash[:12]}.json"
    output_path = output_dir / filename

    full_record = {
        "evidence_package": package.to_canonical_dict(),
        "evidence_sha256": evidence_hash,
        "canonical_json": package.canonical_json(),
    }

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(full_record, f, indent=2)

    return output_path
