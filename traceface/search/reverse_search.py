"""
TraceFace — Reverse Image Search Fallback
==========================================
Ported from: JARVIS/backend/identification/reverse_search.py
Original source: https://github.com/affaan-m/JARVIS (license: unverified)

Uses PicImageSearch library to query Google, Yandex, and Bing simultaneously.
No API keys required. Pure HTTP.

Install: pip install PicImageSearch
"""
from __future__ import annotations

import asyncio
import re
from typing import Any

from traceface.search.models import SearchMatch, SearchResult

_ENGINE_TIMEOUT = 25  # seconds per engine


class ReverseImageSearcher:
    """
    Reverse image search across multiple engines via PicImageSearch.

    Ported from JARVIS/backend/identification/reverse_search.py.
    Original source: https://github.com/affaan-m/JARVIS
    Engines: Google, Yandex, Bing (run in parallel, results merged and deduplicated).
    """

    def __init__(self, engines: list[str] | None = None) -> None:
        self._engines = engines or ["google", "yandex", "bing"]

    @property
    def configured(self) -> bool:
        return True  # No API keys required

    async def search(self, image_bytes: bytes) -> SearchResult:
        """
        Search for a face across multiple reverse image search engines.

        Args:
            image_bytes: Raw bytes of the face image

        Returns:
            SearchResult with matches from all engines (deduplicated by URL)
        """
        tasks = [self._search_engine(engine, image_bytes) for engine in self._engines]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        all_matches: list[SearchMatch] = []
        errors: list[str] = []

        for engine, result in zip(self._engines, results):
            if isinstance(result, Exception):
                print(f"[ReverseSearch] {engine} failed: {result}")
                errors.append(f"{engine}: {result}")
            elif result:
                all_matches.extend(result)

        # Deduplicate by URL
        seen_urls: set[str] = set()
        unique_matches: list[SearchMatch] = []
        for match in all_matches:
            if match.url and match.url not in seen_urls:
                seen_urls.add(match.url)
                unique_matches.append(match)

        # Sort by similarity descending
        unique_matches.sort(key=lambda m: m.similarity, reverse=True)

        success = len(unique_matches) > 0
        error_msg = "; ".join(errors) if errors and not unique_matches else None

        if unique_matches:
            print(f"[ReverseSearch] {len(unique_matches)} unique matches across {len(self._engines)} engines")
        else:
            engines_tried = ", ".join(self._engines)
            print(f"[ReverseSearch] No matches from: {engines_tried}")

        return SearchResult(
            matches=unique_matches[:30],
            success=success,
            error=error_msg,
            provider="reverse_image_search",
        )

    async def _search_engine(
        self, engine: str, image_bytes: bytes
    ) -> list[SearchMatch]:
        try:
            return await asyncio.wait_for(
                self._do_engine_search(engine, image_bytes),
                timeout=_ENGINE_TIMEOUT,
            )
        except TimeoutError:
            print(f"[ReverseSearch] {engine} timed out after {_ENGINE_TIMEOUT}s")
            raise
        except Exception as e:
            raise e

    async def _do_engine_search(
        self, engine: str, image_bytes: bytes
    ) -> list[SearchMatch]:
        """Run a single engine search via PicImageSearch."""
        engine_class = _get_engine_class(engine)
        if engine_class is None:
            print(f"[ReverseSearch] {engine} engine class not available")
            return []

        searcher = engine_class()

        try:
            # PicImageSearch v3.8+ accepts: url, file (str|bytes|Path)
            # Pass raw bytes directly — no BytesIO wrapper needed
            result = await searcher.search(file=image_bytes)
        except Exception as e:
            print(f"[ReverseSearch] {engine} search() raised: {e}")
            raise

        if not result or not result.raw:
            return []

        return _parse_engine_results(engine, result.raw)


def _get_engine_class(engine: str) -> Any:
    """Load PicImageSearch engine class."""
    try:
        if engine == "google":
            from PicImageSearch import Google
            return Google
        elif engine == "yandex":
            from PicImageSearch import Yandex
            return Yandex
        elif engine == "bing":
            from PicImageSearch import Bing
            return Bing
    except ImportError:
        print(f"[ReverseSearch] PicImageSearch not installed. Run: pip install PicImageSearch")
    return None


def _parse_engine_results(engine: str, raw_results: list[Any]) -> list[SearchMatch]:
    """
    Parse raw PicImageSearch results into SearchMatch objects.
    Ported from JARVIS identification/reverse_search.py _parse_engine_results().
    """
    matches: list[SearchMatch] = []
    for item in raw_results[:15]:
        url = getattr(item, "url", "") or ""
        if not url:
            continue

        thumbnail = getattr(item, "thumbnail", None)
        title = getattr(item, "title", "") or ""
        similarity_raw = getattr(item, "similarity", 0.5)

        if isinstance(similarity_raw, str):
            try:
                similarity = float(similarity_raw.strip("%")) / 100.0
            except ValueError:
                similarity = 0.5
        else:
            similarity = float(similarity_raw) if similarity_raw else 0.5

        person_name = _extract_name_from_title(title)

        matches.append(SearchMatch(
            url=url,
            thumbnail_url=thumbnail,
            similarity=max(0.0, min(1.0, similarity)),
            source=engine,
            person_name=person_name,
        ))
    return matches


def _extract_name_from_title(title: str) -> str | None:
    """
    Best-effort name extraction from a search result title.
    Ported from JARVIS identification/reverse_search.py _extract_name_from_title().
    """
    if not title:
        return None

    # Strip parenthetical handles like (@jdoe)
    title = re.sub(r"\s*\(@?\w+\)", "", title)

    # Strip trailing platform names
    cleaned = re.split(
        r"\s*[-|–—/\\]\s*(?:LinkedIn|Twitter|X|Instagram|Facebook|YouTube|Reddit)",
        title
    )
    candidate = cleaned[0].strip() if cleaned else title.strip()

    # Basic heuristic: 2–4 capitalized words
    words = candidate.split()
    if 2 <= len(words) <= 4 and all(w[0].isupper() for w in words if w):
        return candidate

    return None
