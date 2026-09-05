"""
TraceFace — Coarse-to-Fine Candidate Filtering
==============================================
Provides lightweight pre-filtering before expensive ArcFace verification.
- Validates image bytes & basic decodability
- Checks minimum face-resolvable dimensions (>= 64x64)
- Eliminates zero-byte responses and non-image payloads
- Prioritizes candidates with multi-provider agreement
"""
from __future__ import annotations

import io
from dataclasses import dataclass
from typing import Optional
from PIL import Image

from traceface.search.models import NormalizedCandidate


@dataclass
class FilterResult:
    """Result of coarse-filtering a candidate image."""
    passed: bool
    reason: str
    width: int = 0
    height: int = 0
    size_bytes: int = 0


def filter_candidate_image(
    image_bytes: bytes | None,
    min_dimension: int = 64,
    max_dimension: int = 8192,
    max_bytes: int = 25 * 1024 * 1024,
) -> FilterResult:
    """
    Lightweight sanity check on candidate image before running InsightFace.
    Avoids running deep ONNX models on corrupt or unresolvable image files.
    """
    if image_bytes is None or len(image_bytes) == 0:
        return FilterResult(passed=False, reason="Empty or missing image bytes")

    size_bytes = len(image_bytes)
    if size_bytes > max_bytes:
        return FilterResult(passed=False, reason=f"Image exceeds size limit ({size_bytes} > {max_bytes})", size_bytes=size_bytes)

    try:
        with Image.open(io.BytesIO(image_bytes)) as img:
            width, height = img.size
            if width < min_dimension or height < min_dimension:
                return FilterResult(
                    passed=False,
                    reason=f"Image too small for face detection ({width}x{height} < {min_dimension})",
                    width=width,
                    height=height,
                    size_bytes=size_bytes,
                )
            if width > max_dimension or height > max_dimension:
                return FilterResult(
                    passed=False,
                    reason=f"Image dimensions exceed maximum ({width}x{height})",
                    width=width,
                    height=height,
                    size_bytes=size_bytes,
                )
            # Check for absurd aspect ratios (e.g. 1x1000 tracking pixels)
            aspect_ratio = max(width, height) / max(1, min(width, height))
            if aspect_ratio > 10.0:
                return FilterResult(
                    passed=False,
                    reason=f"Extreme aspect ratio ({aspect_ratio:.1f} > 10.0)",
                    width=width,
                    height=height,
                    size_bytes=size_bytes,
                )

            return FilterResult(
                passed=True,
                reason="OK",
                width=width,
                height=height,
                size_bytes=size_bytes,
            )
    except Exception as e:
        return FilterResult(
            passed=False,
            reason=f"Image decoding failed: {e}",
            size_bytes=size_bytes,
        )


def rank_candidates_coarse(
    candidates: list[NormalizedCandidate],
    max_candidates: int = 15,
) -> list[NormalizedCandidate]:
    """
    Coarse pre-selection of top candidates before deep verification.
    Ranks by:
    1. Multi-provider agreement (number of independent engines)
    2. Initial search engine relevance
    """
    ranked = sorted(
        candidates,
        key=lambda c: (-len(c.providers), -round(c.initial_similarity, 4))
    )
    return ranked[:max_candidates]
