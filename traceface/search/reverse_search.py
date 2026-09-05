"""
TraceFace — Reverse Image Search (Multi-Engine Fan-out)
=======================================================
Ported from: JARVIS/backend/identification/reverse_search.py
Original source: https://github.com/affaan-m/JARVIS (license: unverified)

Uses PicImageSearch library to query Google, Yandex, and Bing.
Captures per-engine latency, status, and failure isolation.
"""
from __future__ import annotations

import asyncio
import re
import time
from datetime import datetime, timezone
from typing import Any

from traceface.search.models import ProviderExecution, SearchMatch, SearchResult

_DEFAULT_ENGINE_TIMEOUT = 25  # seconds per engine


class ReverseImageSearcher:
    """
    Reverse image search across multiple engines via PicImageSearch.
    Supports individual or parallel execution across Google, Yandex, Bing.
    """

    def __init__(
        self,
        engines: list[str] | None = None,
        timeout: int = _DEFAULT_ENGINE_TIMEOUT,
    ) -> None:
        self._engines = engines or ["google", "yandex", "bing"]
        self._timeout = timeout

    @property
    def configured(self) -> bool:
        return True  # No API keys required

    async def search_single_engine(
        self, engine: str, image_bytes: bytes
    ) -> tuple[str, ProviderExecution, list[SearchMatch]]:
        """
        Execute search on a single engine with isolated error handling and latency tracking.
        """
        start_time = time.monotonic()
        discovery_ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

        try:
            matches = await asyncio.wait_for(
                self._do_engine_search(engine, image_bytes, discovery_ts),
                timeout=self._timeout,
            )
            latency_ms = int((time.monotonic() - start_time) * 1000)

            if matches:
                status = "success"
                error = None
            else:
                status = "empty"
                error = None

            exec_info = ProviderExecution(
                provider=engine,
                status=status,
                latency_ms=latency_ms,
                matches_count=len(matches),
                error=error,
            )
            return engine, exec_info, matches

        except asyncio.TimeoutError:
            latency_ms = int((time.monotonic() - start_time) * 1000)
            exec_info = ProviderExecution(
                provider=engine,
                status="timeout",
                latency_ms=latency_ms,
                matches_count=0,
                error=f"Timeout after {self._timeout}s",
            )
            return engine, exec_info, []

        except Exception as e:
            latency_ms = int((time.monotonic() - start_time) * 1000)
            exec_info = ProviderExecution(
                provider=engine,
                status="error",
                latency_ms=latency_ms,
                matches_count=0,
                error=str(e),
            )
            return engine, exec_info, []

    async def search(self, image_bytes: bytes) -> SearchResult:
        """
        Search for a face across configured reverse image search engines concurrently.
        """
        start_wall = time.monotonic()
        tasks = [self.search_single_engine(engine, image_bytes) for engine in self._engines]
        results = await asyncio.gather(*tasks)

        all_matches: list[SearchMatch] = []
        provider_runs: dict[str, ProviderExecution] = {}

        for engine, exec_info, matches in results:
            provider_runs[engine] = exec_info
            all_matches.extend(matches)

        total_latency_ms = int((time.monotonic() - start_wall) * 1000)
        success = len(all_matches) > 0
        error_msg = None
        if not success:
            failed_reasons = [f"{e}: {info.status} ({info.error or 'no matches'})" for e, info in provider_runs.items()]
            error_msg = " | ".join(failed_reasons)

        return SearchResult(
            matches=all_matches,
            provider_runs=provider_runs,
            total_latency_ms=total_latency_ms,
            success=success,
            error=error_msg,
            provider="reverse_image_search",
        )

    async def _do_engine_search(
        self, engine: str, image_bytes: bytes, discovery_ts: str
    ) -> list[SearchMatch]:
        """Run a single engine search via PicImageSearch."""
        engine_class = _get_engine_class(engine)
        if engine_class is None:
            return []

        searcher = engine_class()

        try:
            result = await searcher.search(file=image_bytes)
        except Exception as e:
            raise e

        if not result or not result.raw:
            return []

        return _parse_engine_results(engine, result.raw, discovery_ts)


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
        pass
    return None


def _parse_engine_results(
    engine: str, raw_results: list[Any], discovery_ts: str
) -> list[SearchMatch]:
    """
    Parse raw PicImageSearch results into SearchMatch objects with metadata.
    """
    matches: list[SearchMatch] = []
    for item in raw_results[:20]:
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
            title=title if title else None,
            page_url=url,
            discovered_at=discovery_ts,
        ))
    return matches


def _extract_name_from_title(title: str) -> str | None:
    """
    Best-effort name extraction from a search result title.
    """
    if not title:
        return None

    # Strip parenthetical handles like (@jdoe)
    title = re.sub(r"\s*\(@?\w+\)", "", title)

    # Strip trailing platform names
    cleaned = re.split(
        r"\s*[-|–—/\\]\s*(?:LinkedIn|Twitter|X|Instagram|Facebook|YouTube|Reddit|Pinterest)",
        title
    )
    candidate = cleaned[0].strip() if cleaned else title.strip()

    # Basic heuristic: 2–4 capitalized words
    words = candidate.split()
    if 2 <= len(words) <= 4 and all(w[0].isupper() for w in words if w):
        return candidate

    return None
