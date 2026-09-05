"""
TraceFace — Dual Fingerprinting (Exact SHA-256 + Perceptual Hash)
================================================================
Implements dual-layer fingerprinting:
1. Exact Cryptographic Hash (SHA-256): Proves byte-for-byte integrity.
2. Perceptual Fingerprint (dHash): Proves visual equivalence across re-encodings.
"""
from __future__ import annotations

import hashlib
import io
from dataclasses import dataclass
from typing import Optional
from PIL import Image


@dataclass
class DualFingerprint:
    """Cryptographic + perceptual visual fingerprint container."""
    exact_sha256: str
    perceptual_hash: Optional[str] = None
    perceptual_algorithm: str = "dhash-64"
    perceptual_bits: int = 64


def compute_exact_sha256(data_bytes: bytes) -> str:
    """Compute standard SHA-256 hex digest for exact byte-level integrity."""
    return hashlib.sha256(data_bytes).hexdigest()


def compute_perceptual_dhash(image_bytes: bytes, hash_size: int = 8) -> Optional[str]:
    """
    Compute deterministic Difference Hash (dHash) for perceptual visual comparison.

    Algorithm:
    1. Convert image to grayscale (L).
    2. Resize to (hash_size + 1, hash_size) using deterministic bilinear filter.
    3. Compare adjacent horizontal pixel values: pixel[col] > pixel[col + 1].
    4. Pack resulting (hash_size * hash_size) bits into a hex string.

    Parameters:
    - hash_size = 8 produces 64 bits (16 hex characters).
    """
    try:
        with Image.open(io.BytesIO(image_bytes)) as img:
            # Step 1: Grayscale
            gray = img.convert("L")
            # Step 2: Resize to (9, 8)
            resized = gray.resize((hash_size + 1, hash_size), Image.Resampling.BILINEAR)
            import numpy as np
            pixels = np.asarray(resized, dtype=np.int32).flatten().tolist()

            # Step 3: Compute difference bits
            diff_bits = 0
            for row in range(hash_size):
                row_offset = row * (hash_size + 1)
                for col in range(hash_size):
                    left = pixels[row_offset + col]
                    right = pixels[row_offset + col + 1]
                    diff_bits = (diff_bits << 1) | (1 if left > right else 0)

            # Step 4: Format as fixed-width hex string
            hex_len = (hash_size * hash_size) // 4
            return f"{diff_bits:0{hex_len}x}"
    except Exception:
        return None


def compute_dual_fingerprint(image_bytes: bytes) -> DualFingerprint:
    """Compute both exact SHA-256 and perceptual dHash for an image."""
    sha = compute_exact_sha256(image_bytes)
    phash = compute_perceptual_dhash(image_bytes)
    return DualFingerprint(
        exact_sha256=sha,
        perceptual_hash=phash,
        perceptual_algorithm="dhash-64",
        perceptual_bits=64,
    )


def perceptual_hamming_distance(hash1: str, hash2: str) -> int:
    """
    Compute Hamming distance between two perceptual hex hashes.
    Distance <= 10 typically indicates visually identical/near-equivalent images.
    """
    if not hash1 or not hash2 or len(hash1) != len(hash2):
        return 999
    val1 = int(hash1, 16)
    val2 = int(hash2, 16)
    return bin(val1 ^ val2).count("1")
