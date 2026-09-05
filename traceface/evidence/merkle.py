"""
TraceFace — Deterministic Merkle Evidence Tree
==============================================
Constructs a cryptographic Merkle binary tree over all investigation candidates
and evidence metadata.

Algorithm & Specifications:
1. Leaf Canonicalization:
   - Each leaf represents an evidence unit (e.g. candidate or investigation metadata).
   - Canonicalized via deterministic JSON (sort_keys=True, separators=(',', ':')).
   - Leaves are deterministically sorted by leaf_id.
2. Domain Separation (RFC 6962-inspired):
   - Leaf hash: SHA256(0x00 || canonical_utf8_bytes)
   - Internal node: SHA256(0x01 || left_child_bytes || right_child_bytes)
   This prevents second-preimage attacks between leaves and intermediate nodes.
3. Odd Node Count Strategy:
   - When a level has an odd count (2k + 1), the last node is paired with itself:
     parent = SHA256(0x01 || last_child || last_child)
4. Audit Path & Inclusion Proofs:
   - Supports cryptographic inclusion proofs for any candidate leaf up to the root.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class MerkleLeaf:
    """A single leaf node in the Merkle Evidence Tree."""
    leaf_id: str
    leaf_type: str                   # e.g., "candidate", "investigation_header"
    data: dict[str, Any]
    canonical_json: str = ""
    leaf_hash: str = ""

    def compute_hash(self) -> str:
        """Compute RFC 6962-inspired domain-separated leaf hash (prefix 0x00)."""
        self.canonical_json = json.dumps(self.data, sort_keys=True, separators=(",", ":"))
        hasher = hashlib.sha256()
        hasher.update(b"\x00")
        hasher.update(self.canonical_json.encode("utf-8"))
        self.leaf_hash = hasher.hexdigest()
        return self.leaf_hash


@dataclass
class ProofStep:
    """A single step in a Merkle inclusion audit path."""
    sibling_hash: str
    position: str                    # "left" or "right"


@dataclass
class MerkleInclusionProof:
    """Cryptographic proof that a specific leaf was included in the Merkle Root."""
    leaf_id: str
    leaf_hash: str
    merkle_root: str
    leaf_index: int
    audit_path: list[ProofStep] = field(default_factory=list)

    def verify(self) -> bool:
        """
        Verify the inclusion proof by computing hash up to the root.
        """
        current_hash = bytes.fromhex(self.leaf_hash)
        for step in self.audit_path:
            sibling = bytes.fromhex(step.sibling_hash)
            hasher = hashlib.sha256()
            hasher.update(b"\x01")
            if step.position == "left":
                hasher.update(sibling)
                hasher.update(current_hash)
            else:
                hasher.update(current_hash)
                hasher.update(sibling)
            current_hash = hasher.digest()

        return current_hash.hex() == self.merkle_root

    def to_dict(self) -> dict:
        return {
            "leaf_id": self.leaf_id,
            "leaf_hash": self.leaf_hash,
            "merkle_root": self.merkle_root,
            "leaf_index": self.leaf_index,
            "audit_path": [
                {"sibling_hash": s.sibling_hash, "position": s.position}
                for s in self.audit_path
            ]
        }


class MerkleTree:
    """
    Deterministic binary Merkle tree for investigation evidence.
    """

    def __init__(self, leaves: list[MerkleLeaf]) -> None:
        # Sort leaves deterministically by leaf_id
        self.leaves = sorted(leaves, key=lambda l: l.leaf_id)
        for leaf in self.leaves:
            if not leaf.leaf_hash:
                leaf.compute_hash()

        self.levels: list[list[str]] = []
        self.root: str = self._build_tree()

    def _hash_internal(self, left_hex: str, right_hex: str) -> str:
        """Hash two child nodes with 0x01 domain separation prefix."""
        hasher = hashlib.sha256()
        hasher.update(b"\x01")
        hasher.update(bytes.fromhex(left_hex))
        hasher.update(bytes.fromhex(right_hex))
        return hasher.hexdigest()

    def _build_tree(self) -> str:
        """Construct tree levels up to the Merkle root."""
        if not self.leaves:
            # Empty tree root definition
            hasher = hashlib.sha256()
            hasher.update(b"\x00empty_tree")
            empty_root = hasher.hexdigest()
            self.levels = [[empty_root]]
            return empty_root

        current_level = [leaf.leaf_hash for leaf in self.leaves]
        self.levels = [current_level]

        if len(current_level) == 1:
            # Single leaf tree: root is the leaf hash
            return current_level[0]

        while len(current_level) > 1:
            next_level: list[str] = []
            for i in range(0, len(current_level), 2):
                left = current_level[i]
                if i + 1 < len(current_level):
                    right = current_level[i + 1]
                else:
                    # Odd count: duplicate last node
                    right = left
                parent = self._hash_internal(left, right)
                next_level.append(parent)
            self.levels.append(next_level)
            current_level = next_level

        return current_level[0]

    def get_inclusion_proof(self, leaf_id: str) -> Optional[MerkleInclusionProof]:
        """
        Generate a Merkle inclusion proof (audit path) for a given leaf_id.
        """
        leaf_idx = -1
        target_leaf: Optional[MerkleLeaf] = None
        for idx, leaf in enumerate(self.leaves):
            if leaf.leaf_id == leaf_id:
                leaf_idx = idx
                target_leaf = leaf
                break

        if leaf_idx == -1 or target_leaf is None:
            return None

        audit_path: list[ProofStep] = []
        idx = leaf_idx

        for level in self.levels[:-1]:
            if idx % 2 == 0:
                # Target is left child, sibling is right
                if idx + 1 < len(level):
                    sibling = level[idx + 1]
                else:
                    sibling = level[idx]  # duplicate self
                audit_path.append(ProofStep(sibling_hash=sibling, position="right"))
            else:
                # Target is right child, sibling is left
                sibling = level[idx - 1]
                audit_path.append(ProofStep(sibling_hash=sibling, position="left"))
            idx //= 2

        return MerkleInclusionProof(
            leaf_id=target_leaf.leaf_id,
            leaf_hash=target_leaf.leaf_hash,
            merkle_root=self.root,
            leaf_index=leaf_idx,
            audit_path=audit_path,
        )

    def to_dict(self) -> dict:
        return {
            "merkle_root": self.root,
            "leaf_count": len(self.leaves),
            "leaves": [
                {
                    "leaf_id": l.leaf_id,
                    "leaf_type": l.leaf_type,
                    "leaf_hash": l.leaf_hash,
                }
                for l in self.leaves
            ]
        }
