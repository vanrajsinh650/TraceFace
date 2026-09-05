"""
TraceFace — Search Manager (Parallel Multi-Provider Orchestrator)
=================================================================
Ported and evolved from: JARVIS/backend/identification/search_manager.py
Original source: https://github.com/affaan-m/JARVIS (license: unverified)

Orchestrates concurrent multi-provider reverse-image search:
- Concurrent fan-out across Yandex, Google, Bing, PimEyes
- Per-provider timeout and failure isolation
- Latency and status tracking per provider
- Deterministic candidate normalization and deduplication
- Multi-provider agreement detection
"""
from __future__ import annotations

import asyncio
import time
from urllib.parse import urlparse

from traceface.search.models import (
    NormalizedCandidate,
    ProviderExecution,
    SearchMatch,
    SearchResult,
)
from traceface.search.normalize import deduplicate_matches
from traceface.search.pimeyes import PimEyesSearcher
from traceface.search.reverse_search import ReverseImageSearcher

# Social/public domains we prefer — more likely to have a real profile/post
PREFERRED_DOMAINS = {
    "instagram.com", "www.instagram.com",
    "twitter.com", "x.com", "www.twitter.com",
    "facebook.com", "www.facebook.com",
    "linkedin.com", "www.linkedin.com",
    "reddit.com", "www.reddit.com",
    "tiktok.com", "www.tiktok.com",
    "youtube.com", "www.youtube.com",
    "fb.ru", "vk.com", "t.me",
}


class SearchManager:
    """
    Concurrent multi-provider face discovery orchestrator.
    Fans out to Yandex, Google, Bing, and PimEyes concurrently.
    """

    def __init__(
        self,
        pimeyes: PimEyesSearcher | None = None,
        reverse: ReverseImageSearcher | None = None,
        engines: list[str] | None = None,
        engine_timeout: int = 25,
    ) -> None:
        self._pimeyes = pimeyes or PimEyesSearcher()
        self._engines = engines or ["yandex", "google", "bing"]
        self._reverse = reverse or ReverseImageSearcher(engines=self._engines, timeout=engine_timeout)

    async def search(self, image_bytes: bytes) -> SearchResult:
        """
        Concurrently search for face across all providers.
        Isolates failures and aggregates provider latency and candidate agreement.
        """
        start_wall = time.monotonic()
        tasks = []

        # 1. Reverse image engines (Yandex, Google, Bing)
        for engine in self._engines:
            tasks.append(self._reverse.search_single_engine(engine, image_bytes))

        # 2. PimEyes (if configured)
        async def _run_pimeyes():
            if not self._pimeyes.configured:
                return "pimeyes", ProviderExecution(
                    provider="pimeyes", status="skipped", latency_ms=0,
                    matches_count=0, error="Cookies not configured"
                ), []
            p_res = await self._pimeyes.search(image_bytes)
            p_exec = p_res.provider_runs.get("pimeyes", ProviderExecution(
                provider="pimeyes", status="success" if p_res.matches else "empty",
                latency_ms=p_res.total_latency_ms, matches_count=len(p_res.matches),
                error=p_res.error
            ))
            return "pimeyes", p_exec, p_res.matches

        tasks.append(_run_pimeyes())

        # Concurrent fan-out with failure isolation
        results = await asyncio.gather(*tasks, return_exceptions=True)

        all_matches: list[SearchMatch] = []
        provider_runs: dict[str, ProviderExecution] = {}

        for item in results:
            if isinstance(item, Exception):
                continue
            provider_name, exec_info, matches = item
            provider_runs[provider_name] = exec_info
            all_matches.extend(matches)

        total_latency_ms = int((time.monotonic() - start_wall) * 1000)

        # Deterministically deduplicate & extract multi-provider agreement
        candidates = deduplicate_matches(all_matches)

        success = len(candidates) > 0
        error_msg = None
        if not success:
            failed_reasons = [
                f"{p}: {info.status}" + (f" ({info.error})" if info.error else "")
                for p, info in provider_runs.items()
            ]
            error_msg = " | ".join(failed_reasons) if failed_reasons else "No matches found"

        successful_providers = [p for p, info in provider_runs.items() if info.status == "success"]
        primary_provider = ",".join(successful_providers) if successful_providers else "none"

        return SearchResult(
            matches=all_matches,
            candidates=candidates,
            provider_runs=provider_runs,
            total_latency_ms=total_latency_ms,
            success=success,
            error=error_msg,
            provider=primary_provider,
        )

    def prioritize_social(self, candidates: list[NormalizedCandidate]) -> list[NormalizedCandidate]:
        """
        Re-rank candidates prioritizing social media and high provider agreement.
        """
        social = []
        other = []
        for cand in candidates:
            domain = cand.source_domain.lower()
            is_social = domain in PREFERRED_DOMAINS or any(domain.endswith(f".{sd}") for sd in PREFERRED_DOMAINS)
            if is_social:
                social.append(cand)
            else:
                other.append(cand)

        # Re-sort each sub-group by provider agreement count descending, then initial similarity
        social.sort(key=lambda c: (-len(c.providers), -round(c.initial_similarity, 4)))
        other.sort(key=lambda c: (-len(c.providers), -round(c.initial_similarity, 4)))
        return social + other

    def best_person_name(self, candidates: list[NormalizedCandidate]) -> str | None:
        """
        Extract consensus person name from candidate metadata.
        """
        if not candidates:
            return None

        name_counts: dict[str, int] = {}
        for cand in candidates:
            if cand.person_name:
                name = cand.person_name.strip()
                name_counts[name] = name_counts.get(name, 0) + 1

        if not name_counts:
            return None

        return max(name_counts, key=name_counts.get)
