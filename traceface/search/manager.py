"""
TraceFace — Search Manager (Waterfall Orchestrator)
=====================================================
Ported from: JARVIS/backend/identification/search_manager.py
Original source: https://github.com/affaan-m/JARVIS (license: unverified)

Strategy: PimEyes first (purpose-built for faces), reverse image search fallback.
"""
from __future__ import annotations

import re
from urllib.parse import urlparse

from traceface.search.models import SearchMatch, SearchResult
from traceface.search.pimeyes import PimEyesSearcher
from traceface.search.reverse_search import ReverseImageSearcher

# Social/public domains we prefer — more likely to have a real profile
PREFERRED_DOMAINS = {
    "instagram.com", "www.instagram.com",
    "twitter.com", "x.com", "www.twitter.com",
    "facebook.com", "www.facebook.com",
    "linkedin.com", "www.linkedin.com",
    "reddit.com", "www.reddit.com",
    "tiktok.com", "www.tiktok.com",
    "youtube.com", "www.youtube.com",
}


class SearchManager:
    """
    Orchestrates face search across PimEyes and reverse image engines.

    Ported from JARVIS/backend/identification/search_manager.py.
    Original source: https://github.com/affaan-m/JARVIS

    Strategy:
    1. PimEyes (purpose-built for face search, returns face-specific results)
    2. Fallback to PicImageSearch (Google, Yandex, Bing — no API keys)
    """

    def __init__(
        self,
        pimeyes: PimEyesSearcher | None = None,
        reverse: ReverseImageSearcher | None = None,
    ) -> None:
        self._pimeyes = pimeyes or PimEyesSearcher()
        self._reverse = reverse or ReverseImageSearcher()

    async def search(self, image_bytes: bytes) -> SearchResult:
        """
        Search for a face: PimEyes first, reverse image search fallback.

        Args:
            image_bytes: Raw bytes of the query face image (crop preferred)

        Returns:
            SearchResult with matches from the first successful provider
        """
        # Tier 1: PimEyes
        print("[Search] Trying PimEyes (primary)...")
        if self._pimeyes.configured:
            pimeyes_result = await self._pimeyes.search(image_bytes)
            if pimeyes_result.success and pimeyes_result.matches:
                print(f"[Search] PimEyes returned {len(pimeyes_result.matches)} matches")
                return pimeyes_result
            else:
                print(f"[Search] PimEyes failed or no matches: {pimeyes_result.error}")
        else:
            print("[Search] PimEyes not configured (no cookies) — skipping")

        # Tier 2: Reverse image search (Google, Yandex, Bing)
        print("[Search] Trying reverse image search (fallback)...")
        reverse_result = await self._reverse.search(image_bytes)
        if reverse_result.success and reverse_result.matches:
            print(f"[Search] Reverse search returned {len(reverse_result.matches)} matches")
            return reverse_result

        # Both failed
        errors = []
        if not self._pimeyes.configured:
            errors.append("PimEyes: not configured")
        if reverse_result.error:
            errors.append(f"ReverseSearch: {reverse_result.error}")

        return SearchResult(
            matches=[],
            success=False,
            error=" | ".join(errors) if errors else "No matches found across any search engine",
            provider="none",
        )

    def prioritize_social(self, matches: list[SearchMatch]) -> list[SearchMatch]:
        """
        Re-rank matches to put preferred social/public domains first.

        Args:
            matches: Raw search results (already sorted by similarity)

        Returns:
            Re-ranked list with social domains first
        """
        preferred = []
        other = []
        for match in matches:
            domain = urlparse(match.url).netloc.lower()
            if domain in PREFERRED_DOMAINS:
                preferred.append(match)
            else:
                other.append(match)
        return preferred + other

    def best_person_name(self, result: SearchResult) -> str | None:
        """
        Extract the most likely person name from search results using frequency analysis.
        Ported from JARVIS search_manager.py best_name_from_results().
        """
        if not result.matches:
            return None

        name_counts: dict[str, int] = {}
        for match in result.matches:
            if match.person_name:
                name = match.person_name.strip()
                name_counts[name] = name_counts.get(name, 0) + 1

        if not name_counts:
            return None

        return max(name_counts, key=name_counts.get)  # type: ignore[arg-type]
