"""
TraceFace — Candidate Normalization & Deduplication
===================================================
Normalizes raw multi-provider search results into canonical candidate objects.
Preserves provider agreement and provenance.
"""
from __future__ import annotations

import re
from typing import Sequence
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from traceface.search.models import NormalizedCandidate, SearchMatch

# Tracking query parameters to strip for canonical URL normalization
_TRACKING_PARAMS = {
    "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
    "fbclid", "gclid", "ref", "source", "yclid", "_openstat",
}


def normalize_url(url: str) -> str:
    """
    Deterministically normalize a URL.
    - lowercase domain
    - strip tracking query params
    - sort remaining query parameters
    - strip fragment
    - strip redundant trailing slash if path is empty
    """
    if not url:
        return ""

    url = url.strip()
    parsed = urlparse(url)
    scheme = parsed.scheme.lower() or "https"
    netloc = parsed.netloc.lower()

    # Remove standard port if specified
    if ":" in netloc:
        host, port = netloc.split(":", 1)
        if (scheme == "http" and port == "80") or (scheme == "https" and port == "443"):
            netloc = host

    # Normalize path
    path = parsed.path or "/"
    # Clean multiple consecutive slashes
    path = re.sub(r"/+", "/", path)

    # Filter and sort query params
    filtered_params = [
        (k, v) for k, v in parse_qsl(parsed.query, keep_blank_values=True)
        if k.lower() not in _TRACKING_PARAMS
    ]
    filtered_params.sort(key=lambda x: (x[0], x[1]))
    clean_query = urlencode(filtered_params)

    # Omit fragment completely
    normalized = urlunparse((scheme, netloc, path, "", clean_query, ""))
    # Strip trailing slash if path is just "/" and no query
    if normalized.endswith("/") and path == "/" and not clean_query:
        normalized = normalized[:-1]

    return normalized


def deduplicate_matches(matches: Sequence[SearchMatch]) -> list[NormalizedCandidate]:
    """
    Deduplicate search matches across providers into NormalizedCandidate objects.

    Deduplication hierarchy:
    1. Canonical URL match
    2. Exact image URL match (when valid)

    Preserves provider agreement (which providers independently found the candidate).
    """
    grouped_by_key: dict[str, dict] = {}

    for match in matches:
        if not match.url:
            continue

        canon_page_url = normalize_url(match.url)
        canon_img_url = normalize_url(match.thumbnail_url or match.url)

        # Primary deduplication key: canonical page URL
        # Secondary fallback key: canonical image URL
        dedup_key = canon_page_url if canon_page_url else canon_img_url
        if not dedup_key:
            continue

        domain = urlparse(canon_page_url).netloc or urlparse(canon_img_url).netloc

        if dedup_key not in grouped_by_key:
            grouped_by_key[dedup_key] = {
                "canonical_url": canon_page_url or canon_img_url,
                "source_domain": domain,
                "image_url": match.thumbnail_url or match.url,
                "page_url": match.url,
                "title": match.title,
                "person_name": match.person_name,
                "providers": set([match.source] if match.source else []),
                "similarity": match.similarity,
                "discovered_at": match.discovered_at,
            }
        else:
            entry = grouped_by_key[dedup_key]
            if match.source:
                entry["providers"].add(match.source)
            if match.similarity > entry["similarity"]:
                entry["similarity"] = match.similarity
            if match.person_name and not entry["person_name"]:
                entry["person_name"] = match.person_name
            if match.title and not entry["title"]:
                entry["title"] = match.title
            if match.thumbnail_url and not entry["image_url"]:
                entry["image_url"] = match.thumbnail_url

    # Sort deterministically by highest initial similarity, then canonical URL
    sorted_entries = sorted(
        grouped_by_key.values(),
        key=lambda e: (-round(e["similarity"], 4), e["canonical_url"])
    )

    candidates: list[NormalizedCandidate] = []
    for idx, entry in enumerate(sorted_entries, start=1):
        candidates.append(
            NormalizedCandidate(
                candidate_id=f"candidate_{idx:02d}",
                canonical_url=entry["canonical_url"],
                source_domain=entry["source_domain"],
                image_url=entry["image_url"],
                page_url=entry["page_url"],
                title=entry["title"],
                person_name=entry["person_name"],
                providers=sorted(list(entry["providers"])),
                initial_similarity=entry["similarity"],
                discovered_at=entry["discovered_at"],
            )
        )

    return candidates
