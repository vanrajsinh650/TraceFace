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
