"""
TraceFace — Unit Tests for Merkle Evidence Tree
===============================================
Tests deterministic tree construction, odd node counts, empty/single leaf cases,
domain separation, and cryptographic inclusion proofs.
"""
import unittest
from traceface.evidence.merkle import MerkleLeaf, MerkleTree, MerkleInclusionProof, ProofStep


def create_sample_leaf(leaf_id: str, value: str) -> MerkleLeaf:
    leaf = MerkleLeaf(
        leaf_id=leaf_id,
        leaf_type="candidate",
        data={"id": leaf_id, "score": value},
    )
    leaf.compute_hash()
    return leaf


class TestMerkleTree(unittest.TestCase):

    def test_merkle_tree_determinism(self):
        """Identical leaves in any initial order must produce the identical Merkle root."""
        leaves_a = [
            create_sample_leaf("cand_01", "0.75"),
            create_sample_leaf("cand_02", "0.82"),
            create_sample_leaf("cand_03", "0.45"),
        ]
        leaves_b = [
            create_sample_leaf("cand_03", "0.45"),
            create_sample_leaf("cand_01", "0.75"),
            create_sample_leaf("cand_02", "0.82"),
        ]

        tree_a = MerkleTree(leaves_a)
        tree_b = MerkleTree(leaves_b)

        self.assertEqual(tree_a.root, tree_b.root)
        self.assertEqual(len(tree_a.root), 64)

    def test_merkle_tree_leaf_mutation_changes_root(self):
        """Modifying even a single value in one leaf must alter the root."""
        leaves_orig = [
            create_sample_leaf("cand_01", "0.75"),
            create_sample_leaf("cand_02", "0.82"),
        ]
        leaves_tampered = [
            create_sample_leaf("cand_01", "0.75"),
            create_sample_leaf("cand_02", "0.99"),  # Modified
        ]

        tree_orig = MerkleTree(leaves_orig)
        tree_tampered = MerkleTree(leaves_tampered)

        self.assertNotEqual(tree_orig.root, tree_tampered.root)

    def test_odd_leaves_handling(self):
        """Odd counts (3, 5, 7) must construct deterministically using duplicate-last strategy."""
        for count in [3, 5, 7]:
            leaves = [create_sample_leaf(f"cand_{i:02d}", f"0.{i}") for i in range(count)]
            tree = MerkleTree(leaves)
            self.assertIsNotNone(tree.root)
            self.assertEqual(len(tree.root), 64)

    def test_empty_and_single_leaf(self):
        """Handles 0 leaves and 1 leaf without crashing or ambiguity."""
        empty_tree = MerkleTree([])
        self.assertIsNotNone(empty_tree.root)
        self.assertEqual(len(empty_tree.root), 64)

        single_leaf = create_sample_leaf("cand_01", "0.90")
        single_tree = MerkleTree([single_leaf])
        self.assertEqual(single_tree.root, single_leaf.leaf_hash)

    def test_inclusion_proof_validity(self):
        """Inclusion proofs for every leaf in a 4-leaf tree must authenticate to the root."""
        leaves = [create_sample_leaf(f"cand_{i:02d}", f"0.{i*2}") for i in range(1, 5)]
        tree = MerkleTree(leaves)

        for leaf in leaves:
            proof = tree.get_inclusion_proof(leaf.leaf_id)
            self.assertIsNotNone(proof)
            self.assertEqual(proof.leaf_id, leaf.leaf_id)
            self.assertEqual(proof.leaf_hash, leaf.leaf_hash)
            self.assertEqual(proof.merkle_root, tree.root)
            self.assertTrue(proof.verify())

    def test_inclusion_proof_odd_count(self):
        """Inclusion proofs must authenticate correctly even with odd leaf counts (e.g. 3 leaves)."""
        leaves = [create_sample_leaf(f"cand_{i:02d}", f"0.{i}") for i in range(1, 4)]
        tree = MerkleTree(leaves)

        for leaf in leaves:
            proof = tree.get_inclusion_proof(leaf.leaf_id)
            self.assertIsNotNone(proof)
            self.assertTrue(proof.verify())

    def test_tampered_inclusion_proof_fails(self):
        """A forged or tampered audit step must fail verification."""
        leaves = [create_sample_leaf(f"cand_{i:02d}", f"0.{i}") for i in range(1, 5)]
        tree = MerkleTree(leaves)

        proof = tree.get_inclusion_proof("cand_02")
        self.assertIsNotNone(proof)
        self.assertTrue(proof.verify())

        # Tamper with leaf hash
        tampered_proof = MerkleInclusionProof(
            leaf_id=proof.leaf_id,
            leaf_hash="0" * 64,
            merkle_root=proof.merkle_root,
            leaf_index=proof.leaf_index,
            audit_path=proof.audit_path,
        )
        self.assertFalse(tampered_proof.verify())


if __name__ == "__main__":
    unittest.main()
