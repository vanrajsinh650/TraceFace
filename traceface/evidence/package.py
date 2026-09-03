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


def hash_image_bytes(image_bytes: bytes) -> str:
    """Compute SHA-256 of raw image bytes. Used for query_image_sha256."""
    return hashlib.sha256(image_bytes).hexdigest()
