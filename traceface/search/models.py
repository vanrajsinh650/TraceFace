"""
TraceFace — Search Result Models
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


@dataclass
class SearchResult:
    """Result from a face search operation."""
    matches: list[SearchMatch] = field(default_factory=list)
    success: bool = True
    error: Optional[str] = None
    provider: str = ""
