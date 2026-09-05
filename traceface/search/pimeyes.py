"""
TraceFace — PimEyes Face Search
================================
Ported from: JARVIS/backend/identification/pimeyes.py
Original source: https://github.com/affaan-m/JARVIS (license: unverified)

PimEyes direct API integration. Requires session cookies from a logged-in
PimEyes account. Cookies file: traceface/search/pimeyes_cookies.json (gitignored).

Flow:
  1. Load session cookies
  2. Upload face image as base64 data URL → get face IDs
  3. Start PREMIUM_SEARCH with face IDs → get searchHash + apiUrl
  4. Poll apiUrl for results (retry until ready)
  5. Resolve proxy/redirect URLs → extract person names
  6. Return SearchResult with matched URLs
"""
from __future__ import annotations

import asyncio
import base64
import json
import re
from io import BytesIO
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

from traceface.search.models import SearchMatch, SearchResult

_BASE_URL = "https://pimeyes.com"
_HEADERS = {
    "Accept": "application/json",
    "X-Requested-With": "XMLHttpRequest",
    "Origin": "https://pimeyes.com",
    "Referer": "https://pimeyes.com/en",
}

# Cookies file is gitignored. Export from browser after logging into PimEyes.
_COOKIES_FILE = Path(__file__).parent / "pimeyes_cookies.json"


class PimEyesSearcher:
    """
    Face searcher using PimEyes direct API.

    Ported from JARVIS/backend/identification/pimeyes.py.
    Original source: https://github.com/affaan-m/JARVIS
    """

    def __init__(self, cookies_path: Path | None = None) -> None:
        self._cookies_path = cookies_path or _COOKIES_FILE
        self._cookies: dict[str, str] | None = None

    @property
    def configured(self) -> bool:
        return self._cookies_path.exists()

    def _load_cookies(self) -> dict[str, str]:
        if self._cookies is not None:
            return self._cookies

        if not self._cookies_path.exists():
            self._cookies = {}
            return self._cookies

        with open(self._cookies_path) as f:
            data = json.load(f)

        if isinstance(data, list):
            # Cookie-Editor / Netscape format: [{name, value, ...}, ...]
            self._cookies = {c["name"]: c["value"] for c in data}
        else:
            # Already a name→value dict
            self._cookies = data

        print(f"[PimEyes] Loaded {len(self._cookies)} cookies from {self._cookies_path.name}")
        return self._cookies

    async def search(self, image_bytes: bytes) -> SearchResult:
        """
        Upload a face image to PimEyes and retrieve matching URLs.
        """
        import time
        from datetime import datetime, timezone
        from traceface.search.models import ProviderExecution

        start_time = time.monotonic()
        discovery_ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

        try:
            import httpx
        except ImportError:
            latency_ms = int((time.monotonic() - start_time) * 1000)
            exec_info = ProviderExecution(
                provider="pimeyes", status="error", latency_ms=latency_ms,
                matches_count=0, error="httpx not installed",
            )
            return SearchResult(
                success=False,
                error="httpx not installed. Run: pip install httpx",
                provider="pimeyes",
                provider_runs={"pimeyes": exec_info},
                total_latency_ms=latency_ms,
            )

        cookies = self._load_cookies()
        if not cookies:
            latency_ms = int((time.monotonic() - start_time) * 1000)
            exec_info = ProviderExecution(
                provider="pimeyes", status="skipped", latency_ms=latency_ms,
                matches_count=0, error="PimEyes cookies not configured",
            )
            return SearchResult(
                success=False,
                error="PimEyes cookies not configured. Add pimeyes_cookies.json.",
                provider="pimeyes",
                provider_runs={"pimeyes": exec_info},
                total_latency_ms=latency_ms,
            )

        # Rotate landscape images to portrait (helps face detection)
        image_bytes = self._ensure_upright(image_bytes)

        timeout = httpx.Timeout(30.0, connect=10.0)
        try:
            async with httpx.AsyncClient(
                timeout=timeout,
                cookies=cookies,
                headers=_HEADERS,
                follow_redirects=True,
            ) as client:
                res = await self._execute_search(client, image_bytes)
                latency_ms = int((time.monotonic() - start_time) * 1000)
                status = "success" if res.matches else ("empty" if res.success else "error")
                exec_info = ProviderExecution(
                    provider="pimeyes",
                    status=status,
                    latency_ms=latency_ms,
                    matches_count=len(res.matches),
                    error=res.error,
                )
                res.provider_runs = {"pimeyes": exec_info}
                res.total_latency_ms = latency_ms
                return res
        except httpx.TimeoutException as e:
            latency_ms = int((time.monotonic() - start_time) * 1000)
            exec_info = ProviderExecution(
                provider="pimeyes", status="timeout", latency_ms=latency_ms,
                matches_count=0, error=f"PimEyes request timed out: {e}",
            )
            return SearchResult(
                success=False,
                error=f"PimEyes request timed out: {e}",
                provider="pimeyes",
                provider_runs={"pimeyes": exec_info},
                total_latency_ms=latency_ms,
            )
        except Exception as e:
            latency_ms = int((time.monotonic() - start_time) * 1000)
            exec_info = ProviderExecution(
                provider="pimeyes", status="error", latency_ms=latency_ms,
                matches_count=0, error=str(e),
            )
            return SearchResult(
                success=False,
                error=f"PimEyes search failed: {e}",
                provider="pimeyes",
                provider_runs={"pimeyes": exec_info},
                total_latency_ms=latency_ms,
            )

    async def _execute_search(self, client, image_bytes: bytes) -> SearchResult:
        """Run the full PimEyes search flow."""
        # Step 1: Upload image
        b64 = base64.b64encode(image_bytes).decode()
        data_url = f"data:image/jpeg;base64,{b64}"

        upload_resp = await client.post(
            f"{_BASE_URL}/api/upload/file",
            json={"image": data_url},
        )
        if upload_resp.status_code != 200:
            return SearchResult(
                success=False,
                error=f"PimEyes upload failed: HTTP {upload_resp.status_code}",
                provider="pimeyes",
            )

        upload_data = upload_resp.json()
        faces = upload_data.get("faces", [])
        if not faces:
            return SearchResult(
                success=False,
                error="PimEyes detected no faces in the uploaded image",
                provider="pimeyes",
            )

        face_ids = [f["id"] for f in faces]
        print(f"[PimEyes] Detected {len(faces)} face(s): {face_ids}")

        # Step 2: Start premium search
        search_resp = await client.post(
            f"{_BASE_URL}/api/search/new",
            json={
                "faces": face_ids,
                "type": "PREMIUM_SEARCH",
                "time": "any",
                "safeSearch": False,
                "deepSearch": False,
                "groups": True,
                "order": "default",
            },
        )
        if search_resp.status_code != 200:
            return SearchResult(
                success=False,
                error=f"PimEyes search start failed: HTTP {search_resp.status_code}",
                provider="pimeyes",
            )

        search_data = search_resp.json()
        search_hash = search_data.get("searchHash", "")
        api_url = search_data.get("apiUrl", "")

        if not search_hash or not api_url:
            return SearchResult(
                success=False,
                error=f"PimEyes: missing searchHash or apiUrl in response: {search_data}",
                provider="pimeyes",
            )

        print(f"[PimEyes] Search started. Hash: {search_hash[:12]}...")

        # Step 3: Fetch results (with retry — async backend)
        raw_results = await self._fetch_results(api_url, search_hash)
        if not raw_results:
            return SearchResult(
                success=False,
                error="PimEyes returned no results",
                provider="pimeyes",
            )

        print(f"[PimEyes] Got {len(raw_results)} raw results. Resolving URLs...")

        # Step 4: Resolve URLs and extract matches
        matches = await self._build_matches(raw_results)

        if not matches:
            return SearchResult(
                success=False,
                error="PimEyes: all result URLs failed to resolve",
                provider="pimeyes",
            )

        print(f"[PimEyes] Resolved {len(matches)} matches.")
        return SearchResult(matches=matches[:30], success=True, provider="pimeyes")

    async def _fetch_results(self, api_url: str, search_hash: str, limit: int = 50) -> list[dict]:
        """
        Fetch results from PimEyes backend with retry.
        Ported from JARVIS identification/pimeyes.py _fetch_results().
        """
        try:
            import httpx
        except ImportError:
            return []

        all_results: list[dict] = []
        max_retries = 5

        async with httpx.AsyncClient(timeout=httpx.Timeout(20.0), follow_redirects=True) as client:
            for attempt in range(max_retries):
                if attempt > 0:
                    wait = 1.0 * (1.5 ** (attempt - 1))  # 1s, 1.5s, 2.25s, 3.4s
                    print(f"[PimEyes] Results not ready, retry {attempt} in {wait:.1f}s")
                    await asyncio.sleep(wait)

                resp = await client.post(
                    api_url,
                    json={"hash": search_hash, "offset": 0, "limit": limit},
                    headers={"Content-Type": "application/json"},
                )
                if resp.status_code != 200:
                    continue

                data = resp.json()
                results = data.get("results", [])
                if results:
                    all_results.extend(results)
                    # Fetch additional pages
                    offset = len(results)
                    while data.get("isMoreResults", False) and len(all_results) < limit:
                        await asyncio.sleep(0.2)
                        page_resp = await client.post(
                            api_url,
                            json={"hash": search_hash, "offset": offset, "limit": 50},
                            headers={"Content-Type": "application/json"},
                        )
                        if page_resp.status_code != 200:
                            break
                        data = page_resp.json()
                        page_results = data.get("results", [])
                        if not page_results:
                            break
                        all_results.extend(page_results)
                        offset += len(page_results)
                    break

        return all_results

    async def _build_matches(self, results: list[dict]) -> list[SearchMatch]:
        """
        Resolve PimEyes proxy URLs and build SearchMatch objects.
        Ported from JARVIS identification/pimeyes.py _resolve_and_build_matches().
        """
        semaphore = asyncio.Semaphore(10)

        async def resolve_one(result: dict) -> Optional[SearchMatch]:
            source_url = result.get("sourceUrl", "")
            thumbnail_url = result.get("thumbnailUrl") or result.get("imageUrl")
            quality = float(result.get("quality", 0))
            domain = result.get("domain", "")

            similarity = quality / 100.0 if quality > 1.0 else quality
            similarity = max(0.0, min(1.0, similarity))

            real_url = source_url
            if source_url:
                async with semaphore:
                    real_url = await self._resolve_redirect(source_url)

            if not real_url:
                return None

            person_name = _extract_name_from_url(real_url, domain)

            return SearchMatch(
                url=real_url,
                thumbnail_url=thumbnail_url,
                similarity=similarity,
                source="pimeyes",
                person_name=person_name,
            )

        tasks = [resolve_one(r) for r in results]
        resolved = await asyncio.gather(*tasks, return_exceptions=True)

        matches: list[SearchMatch] = []
        for item in resolved:
            if isinstance(item, SearchMatch):
                matches.append(item)
        return matches

    @staticmethod
    async def _resolve_redirect(url: str) -> str:
        """Follow redirect to get the real destination URL."""
        try:
            import httpx
            async with httpx.AsyncClient(timeout=httpx.Timeout(10.0), follow_redirects=True) as client:
                resp = await client.head(url)
                return str(resp.url)
        except Exception:
            try:
                import httpx
                async with httpx.AsyncClient(timeout=httpx.Timeout(10.0), follow_redirects=True) as client:
                    resp = await client.get(url)
                    return str(resp.url)
            except Exception:
                return url

    @staticmethod
    def _ensure_upright(image_bytes: bytes) -> bytes:
        """Rotate landscape images to portrait for better face detection."""
        try:
            from PIL import Image as PILImage
            img = PILImage.open(BytesIO(image_bytes))
            w, h = img.size
            if w > h:
                img = img.rotate(90, expand=True)
                buf = BytesIO()
                img.save(buf, format="JPEG", quality=90)
                return buf.getvalue()
        except Exception:
            pass
        return image_bytes


def _extract_name_from_url(url: str, domain: str) -> Optional[str]:
    """
    Best-effort person name extraction from a resolved URL.
    Ported from JARVIS identification/pimeyes.py _extract_name_from_url().
    """
    parsed = urlparse(url)
    path = parsed.path.strip("/")

    # LinkedIn: /in/john-doe → "John Doe"
    if "linkedin.com" in url:
        match = re.search(r"/in/([^/?]+)", path)
        if match:
            slug = match.group(1)
            name = slug.replace("-", " ").title()
            if len(name) > 3 and not name.startswith("Http"):
                return name

    # Facebook: /people/John-Doe
    if "facebook.com" in url:
        match = re.search(r"/people/([^/?]+)", path)
        if match:
            return match.group(1).replace("-", " ").title()

    return None
