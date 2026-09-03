"""
TraceFace — Search Manager (Waterfall Orchestrator)
=====================================================
Ported from: JARVIS/backend/identification/search_manager.py
Original source: https://github.com/affaan-m/JARVIS (license: unverified)

Strategy: PimEyes first (purpose-built for faces), reverse image search fallback.
"""
from __future__ import annotations

from traceface.search.models import SearchMatch, SearchResult
from traceface.search.pimeyes import PimEyesSearcher
from traceface.search.reverse_search import ReverseImageSearcher


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
