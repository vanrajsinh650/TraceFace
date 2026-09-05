"""
TraceFace — Search Result Models
=================================
Provable search results and provider metadata for evidence ledger.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class SearchMatch:
    """A single match from reverse face search."""
    url: str
    thumbnail_url: Optional[str] = None
    similarity: float = 0.5         # 0.0–1.0
    source: str = ""                # e.g., "pimeyes", "google", "yandex", "bing"
    person_name: Optional[str] = None
    title: Optional[str] = None
    page_url: Optional[str] = None
    discovered_at: Optional[str] = None


@dataclass
class ProviderExecution:
    """Execution telemetry and status for an individual search provider."""
    provider: str
    status: str                     # "success", "empty", "timeout", "error", "skipped"
    latency_ms: int = 0
    matches_count: int = 0
    error: Optional[str] = None


@dataclass
class NormalizedCandidate:
    """
    Deduplicated search candidate discovered across one or more search engines.
    """
    candidate_id: str
    canonical_url: str
    source_domain: str
    image_url: str
    page_url: str
    title: Optional[str] = None
    person_name: Optional[str] = None
    providers: list[str] = field(default_factory=list)
    initial_similarity: float = 0.5
    discovered_at: Optional[str] = None


@dataclass
class SearchResult:
    """Aggregated result from a multi-provider search operation."""
    matches: list[SearchMatch] = field(default_factory=list)
    candidates: list[NormalizedCandidate] = field(default_factory=list)
    provider_runs: dict[str, ProviderExecution] = field(default_factory=dict)
    total_latency_ms: int = 0
    success: bool = True
    error: Optional[str] = None
    provider: str = ""
