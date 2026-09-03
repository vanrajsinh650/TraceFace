"""
TraceFace — Face Detection & Embedding
======================================
Source: eye_of_web/src/lib/init_insightface.py (MIT — Mehmet Yüksel Şekeroğlu)
Adapted: InsightFace FaceAnalysis init + ArcFace embedding extraction.

Uses InsightFace buffalo_l model (auto-downloads ~280MB on first run).
Each detected face.embedding is a 512-dim ArcFace vector.
"""
from __future__ import annotations

import io
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import numpy as np

# ---------------------------------------------------------------------------
# Type stubs to allow import without insightface installed at type-check time
# ---------------------------------------------------------------------------
try:
    import insightface
    import insightface.app
    _INSIGHTFACE_AVAILABLE = True
except ImportError:
    _INSIGHTFACE_AVAILABLE = False

try:
    from PIL import Image
    _PIL_AVAILABLE = True
except ImportError:
    _PIL_AVAILABLE = False


@dataclass
class DetectedFace:
    """A face detected in an image with its ArcFace embedding."""
    bbox: tuple[int, int, int, int]          # (x1, y1, x2, y2) absolute pixels
    confidence: float
    embedding: list[float]                   # 512-dim ArcFace vector
    landmark: Optional[np.ndarray] = None   # 5-point keypoints if available


@dataclass
class DetectionResult:
    """Result of face detection on an image."""
    faces: list[DetectedFace] = field(default_factory=list)
    image_width: int = 0
    image_height: int = 0
    success: bool = True
    error: Optional[str] = None

    @property
    def primary_face(self) -> Optional[DetectedFace]:
        """Return the largest face by bounding box area (most likely the subject)."""
        if not self.faces:
            return None
        return max(
            self.faces,
            key=lambda f: (f.bbox[2] - f.bbox[0]) * (f.bbox[3] - f.bbox[1])
        )


# ---------------------------------------------------------------------------
# InsightFace initialization (from eye_of_web init_insightface.py)
# ---------------------------------------------------------------------------
_DEFAULT_MODEL = "buffalo_l"
_DEFAULT_DET_THRESH = 0.5
_DEFAULT_DET_SIZE = (640, 640)
_DEFAULT_CTX_ID = 0
_DEFAULT_PROVIDERS = ["CPUExecutionProvider"]


def _init_insightface_app(
    model_name: str = _DEFAULT_MODEL,
    det_thresh: float = _DEFAULT_DET_THRESH,
    det_size: tuple[int, int] = _DEFAULT_DET_SIZE,
    ctx_id: int = _DEFAULT_CTX_ID,
    providers: list[str] | None = None,
) -> "insightface.app.FaceAnalysis | None":
    """
    Initialize InsightFace FaceAnalysis.

    Adapted from: eye_of_web/src/lib/init_insightface.py — initilate_insightface()
    Original author: Mehmet Yüksel Şekeroğlu (MIT License)

    buffalo_l auto-downloads to ~/.insightface/models/buffalo_l/ on first call.
    """
    if not _INSIGHTFACE_AVAILABLE:
        return None

    if providers is None:
        providers = _DEFAULT_PROVIDERS

    # Allow GPU via env var
    if os.environ.get("INSIGHTFACE_GPU", "0") == "1":
        providers = ["CUDAExecutionProvider", "CPUExecutionProvider"]

    model = os.environ.get("INSIGHTFACE_MODEL", model_name)
    thresh = float(os.environ.get("INSIGHTFACE_DET_THRESH", str(det_thresh)))

    try:
        app = insightface.app.FaceAnalysis(name=model, providers=providers)
        app.prepare(ctx_id=ctx_id, det_thresh=thresh, det_size=det_size)
        return app
    except FileNotFoundError as e:
        print(f"[ERROR] InsightFace model files not found: {e}")
        return None
    except Exception as e:
        print(f"[ERROR] InsightFace init failed: {e}")
        import traceback
        traceback.print_exc()
        return None
