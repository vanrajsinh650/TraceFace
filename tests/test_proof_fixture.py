"""Tests for the public proof fixture — cryptographic consistency and security."""
import copy
import json
import os
import unittest
from pathlib import Path

FIXTURE_PATH = Path(__file__).resolve().parent.parent / "fixtures" / "demo_evidence.json"


class TestProofFixture(unittest.TestCase):
    """Verify the public proof fixture is cryptographically valid and contains no secrets."""

    @classmethod
    def setUpClass(cls):
        if not FIXTURE_PATH.exists():
            raise unittest.SkipTest(f"Fixture not found: {FIXTURE_PATH}")
        cls.raw = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
        cls.pkg_data = cls.raw["evidence_package"]

    # ── Structure ──────────────────────────────────────────────────────────

    def test_fixture_exists_and_loads(self):
        """Fixture file exists and contains required top-level keys."""
        self.assertIn("evidence_package", self.raw)
        self.assertIn("evidence_sha256", self.raw)
        self.assertIn("merkle_root", self.raw)
        self.assertIn("_proof_metadata", self.raw)

    def test_proof_metadata_fields(self):
        """Proof metadata contains required public blockchain references."""
        meta = self.raw["_proof_metadata"]
        self.assertEqual(meta["chain_id"], 11155111)
        self.assertEqual(meta["network"], "Ethereum Sepolia")
        self.assertFalse(meta["requires_private_key"])
        self.assertEqual(meta["verification_mode"], "read-only")
        self.assertIn("contract_address", meta)
        self.assertIn("anchor_tx", meta)

    # ── Cryptographic Consistency ──────────────────────────────────────────

    def test_fixture_merkle_root_reconstruction(self):
        """Recomputed Merkle root matches stored root — proves fixture is genuine."""
        from traceface.evidence.package import load_evidence_package

        pkg, _ = load_evidence_package(str(FIXTURE_PATH))
        result = pkg.recompute_merkle_root()
        recomputed_root = result[0] if isinstance(result, tuple) else result
        self.assertEqual(
            recomputed_root,
            self.raw["merkle_root"],
            "Merkle root mismatch: fixture data may have been altered",
        )

    def test_fixture_evidence_sha256(self):
        """Recomputed SHA-256 matches stored hash — proves canonical integrity."""
        from traceface.evidence.package import load_evidence_package

        pkg, _ = load_evidence_package(str(FIXTURE_PATH))
        self.assertEqual(
            pkg.sha256(),
            self.raw["evidence_sha256"],
            "Evidence SHA-256 mismatch: canonical representation has changed",
        )

    def test_fixture_inclusion_proof_valid(self):
        """Merkle inclusion proof authenticates the matched candidate."""
        from traceface.evidence.merkle import MerkleInclusionProof, ProofStep
        from traceface.evidence.package import load_evidence_package

        pkg, _ = load_evidence_package(str(FIXTURE_PATH))
        proof_data = pkg.matched_inclusion_proof
        self.assertIsNotNone(proof_data, "No inclusion proof in fixture")

        result = pkg.recompute_merkle_root()
        recomputed_root = result[0] if isinstance(result, tuple) else result

        steps = [ProofStep(s["sibling_hash"], s["position"]) for s in proof_data["audit_path"]]
        proof = MerkleInclusionProof(
            leaf_id=proof_data["leaf_id"],
            leaf_hash=proof_data["leaf_hash"],
            merkle_root=recomputed_root,
            leaf_index=proof_data["leaf_index"],
            audit_path=steps,
        )
        self.assertTrue(proof.verify(), "Inclusion proof does not authenticate")

    def test_modified_fixture_fails(self):
        """Altering a candidate field must break the Merkle root — proves real verification."""
        from traceface.evidence.package import load_evidence_package

        # Create a tampered copy
        tampered = copy.deepcopy(self.raw)
        candidates = tampered["evidence_package"]["candidates"]
        if candidates:
            candidates[0]["face_similarity_score"] = 0.999999
        tampered_path = FIXTURE_PATH.parent / "_test_tampered.json"
        try:
            tampered_path.write_text(json.dumps(tampered), encoding="utf-8")
            pkg, _ = load_evidence_package(str(tampered_path))
            result = pkg.recompute_merkle_root()
            recomputed_root = result[0] if isinstance(result, tuple) else result
            self.assertNotEqual(
                recomputed_root,
                tampered["merkle_root"],
                "Tampered fixture should NOT produce the same Merkle root",
            )
        finally:
            tampered_path.unlink(missing_ok=True)

    # ── Security ───────────────────────────────────────────────────────────

    def test_fixture_no_secrets(self):
        """Fixture must not contain private keys, mnemonics, API keys, or local paths."""
        content = FIXTURE_PATH.read_text(encoding="utf-8")
        forbidden = [
            "PRIVATE_KEY",
            "MNEMONIC",
            "API_KEY",
            "SECRET",
            "file:///home",
            "/home/vanrajsinh",
        ]
        for word in forbidden:
            self.assertNotIn(
                word, content, f"Fixture contains forbidden content: {word}"
            )

    def test_no_private_key_required(self):
        """Proof metadata explicitly declares no private key is required."""
        meta = self.raw["_proof_metadata"]
        self.assertFalse(meta.get("requires_private_key", True))


if __name__ == "__main__":
    unittest.main()

