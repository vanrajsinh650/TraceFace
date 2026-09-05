"""
TraceFace — Unit Tests for Dual Fingerprinting
===============================================
Tests exact SHA-256 byte-level hashing and perceptual dHash image fingerprinting.
"""
import io
import unittest
from PIL import Image, ImageDraw
from traceface.evidence.fingerprint import (
    compute_exact_sha256,
    compute_perceptual_dhash,
    compute_dual_fingerprint,
    perceptual_hamming_distance,
)


def _generate_test_image(pattern: str = "cross", size: tuple[int, int] = (200, 200)) -> bytes:
    """Generate deterministic test image in memory."""
    img = Image.new("RGB", size, color="white")
    draw = ImageDraw.Draw(img)
    if pattern == "cross":
        draw.line((0, 0, size[0], size[1]), fill="black", width=5)
        draw.line((0, size[1], size[0], 0), fill="black", width=5)
    elif pattern == "circle":
        draw.ellipse((20, 20, size[0] - 20, size[1] - 20), fill="blue")
    else:
        draw.rectangle((50, 50, 150, 150), fill="red")

    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=95)
    return buf.getvalue()


class TestFingerprints(unittest.TestCase):

    def test_exact_sha256_determinism(self):
        data = b"TraceFace Cryptographic Fingerprint Verification Test"
        hash1 = compute_exact_sha256(data)
        hash2 = compute_exact_sha256(data)
        self.assertEqual(hash1, hash2)
        self.assertEqual(len(hash1), 64)

        # Altering 1 byte alters the hash completely
        hash_altered = compute_exact_sha256(data + b"!")
        self.assertNotEqual(hash1, hash_altered)

    def test_perceptual_dhash_consistency(self):
        img_bytes1 = _generate_test_image("cross")
        img_bytes2 = _generate_test_image("cross")

        dhash1 = compute_perceptual_dhash(img_bytes1)
        dhash2 = compute_perceptual_dhash(img_bytes2)

        self.assertIsNotNone(dhash1)
        self.assertEqual(dhash1, dhash2)
        self.assertEqual(len(dhash1), 16)
        self.assertEqual(perceptual_hamming_distance(dhash1, dhash2), 0)

    def test_perceptual_dhash_different_images(self):
        cross_bytes = _generate_test_image("cross")
        circle_bytes = _generate_test_image("circle")

        dhash_cross = compute_perceptual_dhash(cross_bytes)
        dhash_circle = compute_perceptual_dhash(circle_bytes)

        self.assertNotEqual(dhash_cross, dhash_circle)
        distance = perceptual_hamming_distance(dhash_cross, dhash_circle)
        self.assertGreater(distance, 5)

    def test_dual_fingerprint_container(self):
        img_bytes = _generate_test_image("cross")
        df = compute_dual_fingerprint(img_bytes)

        self.assertIsNotNone(df.exact_sha256)
        self.assertEqual(len(df.exact_sha256), 64)
        self.assertIsNotNone(df.perceptual_hash)
        self.assertEqual(len(df.perceptual_hash), 16)
        self.assertEqual(df.perceptual_algorithm, "dhash-64")


if __name__ == "__main__":
    unittest.main()
