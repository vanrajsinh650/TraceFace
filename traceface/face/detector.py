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


# ---------------------------------------------------------------------------
# FaceDetector — main class
# ---------------------------------------------------------------------------

class FaceDetector:
    """
    Face detector and embedder using InsightFace buffalo_l (ArcFace).

    Uses the same FaceAnalysis setup as eye_of_web/src/lib/init_insightface.py.
    Detects all faces in an image and returns per-face 512-dim ArcFace embeddings.

    Usage:
        detector = FaceDetector()
        result = detector.detect(image_bytes)
        query_face = result.primary_face  # largest face
        embedding = query_face.embedding  # 512-dim list[float]
    """

    def __init__(
        self,
        det_thresh: float = _DEFAULT_DET_THRESH,
        det_size: tuple[int, int] = _DEFAULT_DET_SIZE,
    ) -> None:
        self._app = _init_insightface_app(
            det_thresh=det_thresh,
            det_size=det_size,
        )
        self._det_thresh = det_thresh

    @property
    def available(self) -> bool:
        return self._app is not None

    def detect(self, image_bytes: bytes) -> DetectionResult:
        """
        Detect all faces in an image and compute ArcFace embeddings.

        Args:
            image_bytes: Raw image bytes (JPEG, PNG, etc.)

        Returns:
            DetectionResult with list of DetectedFace objects.
        """
        if not self.available:
            return DetectionResult(
                success=False,
                error="InsightFace is not available. Install: pip install insightface onnxruntime"
            )

        # Decode image to numpy array (RGB)
        try:
            import cv2
            img_array = np.frombuffer(image_bytes, np.uint8)
            img_bgr = cv2.imdecode(img_array, cv2.IMREAD_COLOR)
            if img_bgr is None:
                raise ValueError("cv2.imdecode returned None — invalid image bytes")
            height, width = img_bgr.shape[:2]
        except Exception as e:
            return DetectionResult(success=False, error=f"Image decode failed: {e}")

        # InsightFace expects BGR numpy array
        try:
            faces_raw = self._app.get(img_bgr)
        except Exception as e:
            return DetectionResult(
                image_width=width,
                image_height=height,
                success=False,
                error=f"InsightFace detection failed: {e}",
            )

        faces: list[DetectedFace] = []
        for face in faces_raw:
            # bbox: [x1, y1, x2, y2] as float32
            bbox_raw = face.bbox.astype(int).tolist()
            bbox = (
                max(0, bbox_raw[0]),
                max(0, bbox_raw[1]),
                min(width, bbox_raw[2]),
                min(height, bbox_raw[3]),
            )

            # det_score: detection confidence
            confidence = float(getattr(face, "det_score", 0.0))

            # embedding: 512-dim ArcFace vector (normalized)
            embedding_raw = getattr(face, "embedding", None)
            if embedding_raw is not None:
                # Normalize to unit vector (ArcFace embeddings should already be L2-normalized)
                norm = np.linalg.norm(embedding_raw)
                if norm > 1e-10:
                    embedding = (embedding_raw / norm).tolist()
                else:
                    embedding = embedding_raw.tolist()
            else:
                embedding = []

            # Landmarks (5-point: eyes, nose, mouth corners)
            landmark = getattr(face, "kps", None)

            faces.append(DetectedFace(
                bbox=bbox,
                confidence=confidence,
                embedding=embedding,
                landmark=landmark,
            ))

        return DetectionResult(
            faces=faces,
            image_width=width,
            image_height=height,
            success=True,
        )

    def detect_from_path(self, image_path: str | Path) -> DetectionResult:
        """Detect faces from a file path."""
        path = Path(image_path)
        if not path.exists():
            return DetectionResult(success=False, error=f"File not found: {path}")
        try:
            image_bytes = path.read_bytes()
        except Exception as e:
            return DetectionResult(success=False, error=f"Failed to read file: {e}")
        return self.detect(image_bytes)
