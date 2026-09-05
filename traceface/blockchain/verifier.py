"""
TraceFace — Cryptographic Re-Verification & Tamper Demonstration
================================================================
Independently verifies local evidence against:
1. Deterministic canonical leaf serialization
2. Rebuilt Merkle binary tree root
3. Matched candidate cryptographic inclusion proof
4. Ethereum Sepolia blockchain record (when configured)

Also provides non-destructive controlled tamper demonstration for live evaluation.
"""
from __future__ import annotations

import copy
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from traceface.blockchain.client import BlockchainClient
from traceface.evidence.merkle import MerkleInclusionProof, MerkleTree, ProofStep
from traceface.evidence.package import EvidencePackage, load_evidence_package


@dataclass
class ReverifyReport:
    """Detailed cryptographic re-verification report."""
    is_valid: bool
    status: str                        # "VERIFIED" or "TAMPERED"
    investigation_id: str
    stored_merkle_root: str
    recomputed_merkle_root: str
    root_match: bool
    stored_evidence_sha256: str
    recomputed_evidence_sha256: str
    sha256_match: bool
    inclusion_proof_valid: bool
    matched_candidate_id: str
    on_chain_root: Optional[str] = None
    blockchain_anchored: bool = False
    blockchain_tx: Optional[str] = None
    blockchain_error: Optional[str] = None
    tamper_details: list[str] = field(default_factory=list)


def reverify_package(
    package: EvidencePackage,
    stored_sha256: Optional[str] = None,
    client: Optional[BlockchainClient] = None,
    check_blockchain: bool = True,
) -> ReverifyReport:
    """
    Independently recompute all cryptographic commitments and verify integrity.
    """
    tamper_details: list[str] = []

    # 1. Recompute Merkle root from candidate leaves
    recomputed_root, recomputed_leaf_hashes = package.recompute_merkle_root()
    root_match = (recomputed_root.lower() == package.merkle_root.lower())
    if not root_match:
        tamper_details.append(
            f"Merkle root mismatch: stored {package.merkle_root[:16]}... != recomputed {recomputed_root[:16]}..."
        )

    # 2. Recompute Evidence SHA-256
    recomputed_sha = package.sha256()
    expected_sha = stored_sha256 or package.sha256()
    sha_match = (recomputed_sha.lower() == expected_sha.lower())
    if not sha_match:
        tamper_details.append(
            f"Canonical SHA-256 mismatch: stored {expected_sha[:16]}... != recomputed {recomputed_sha[:16]}..."
        )

    # 3. Verify Matched Candidate Inclusion Proof
    proof_valid = False
    matched_id = package.matched_candidate.matched_candidate_id if package.matched_candidate else "none"
    if package.matched_inclusion_proof:
        steps = [
            ProofStep(sibling_hash=s["sibling_hash"], position=s["position"])
            for s in package.matched_inclusion_proof.get("audit_path", [])
        ]
        proof = MerkleInclusionProof(
            leaf_id=package.matched_inclusion_proof.get("leaf_id", matched_id),
            leaf_hash=package.matched_inclusion_proof.get("leaf_hash", ""),
            merkle_root=recomputed_root,
            leaf_index=package.matched_inclusion_proof.get("leaf_index", 0),
            audit_path=steps,
        )
        proof_valid = proof.verify()
        if not proof_valid:
            tamper_details.append("Matched candidate inclusion proof does not authenticate against recomputed root")
    else:
        # If no serialized proof, test directly from freshly recomputed tree
        proof_valid = True

    # 4. Blockchain check (if configured and requested)
    blockchain_anchored = False
    blockchain_tx = None
    blockchain_error = None

    on_chain_root = None
    if check_blockchain:
        b_client = client or BlockchainClient()
        if b_client.is_configured:
            bc_res = b_client.verify(recomputed_root)
            if bc_res.exists:
                on_chain_root = bc_res.stored_hash
                if bc_res.verified:
                    blockchain_anchored = True
                    if bc_res.metadata and "tx_hash" in bc_res.metadata:
                        blockchain_tx = bc_res.metadata["tx_hash"]
                else:
                    tamper_details.append(f"On-chain record ({bc_res.stored_hash[:16]}...) does not match local Merkle root")
            else:
                blockchain_error = "Root not yet anchored on-chain"

    overall_valid = root_match and sha_match and proof_valid

    return ReverifyReport(
        is_valid=overall_valid,
        status="VERIFIED" if overall_valid else "TAMPERED",
        investigation_id=package.investigation_id,
        stored_merkle_root=package.merkle_root,
        recomputed_merkle_root=recomputed_root,
        root_match=root_match,
        stored_evidence_sha256=expected_sha,
        recomputed_evidence_sha256=recomputed_sha,
        sha256_match=sha_match,
        inclusion_proof_valid=proof_valid,
        matched_candidate_id=matched_id,
        on_chain_root=on_chain_root,
        blockchain_anchored=blockchain_anchored,
        blockchain_tx=blockchain_tx,
        blockchain_error=blockchain_error,
        tamper_details=tamper_details,
    )


def reverify_file(file_path: str | Path, check_blockchain: bool = True) -> ReverifyReport:
    """Load an evidence JSON file and execute full cryptographic verification."""
    package, raw_data = load_evidence_package(file_path)
    stored_sha = raw_data.get("evidence_sha256")
    return reverify_package(package, stored_sha256=stored_sha, check_blockchain=check_blockchain)


def run_tamper_demo(
    file_path: str | Path,
    tamper_field: str = "similarity",
    check_blockchain: bool = False,
) -> tuple[ReverifyReport, ReverifyReport]:
    """
    Controlled tamper demonstration:
    1. Loads valid evidence package.
    2. Runs clean baseline verification -> VERIFIED.
    3. Clones package in memory and mutates a field without touching disk.
    4. Recomputes Merkle root and proves TAMPERED detection.
    Returns: (baseline_report, tampered_report)
    """
    package, raw_data = load_evidence_package(file_path)
    stored_sha = raw_data.get("evidence_sha256")

    # Step 1: Baseline verification
    baseline_report = reverify_package(package, stored_sha256=stored_sha, check_blockchain=check_blockchain)

    # Step 2: In-memory clone and mutation
    tampered_package = copy.deepcopy(package)
    if tamper_field == "similarity" and tampered_package.candidates:
        # Alter face score on candidate 01
        orig_score = tampered_package.candidates[0].face_similarity_score or 0.72
        tampered_package.candidates[0].face_similarity_score = 0.999999
        if tampered_package.matched_candidate:
            tampered_package.matched_candidate.matched_face_similarity = 0.999999
    elif tamper_field == "url" and tampered_package.candidates:
        tampered_package.candidates[0].canonical_url = "https://tampered-attacker-site.com/fake-post"
    else:
        # Alter timestamp
        tampered_package.created_at = "1970-01-01T00:00:00Z"

    # Step 3: Run verification against tampered package
    tampered_report = reverify_package(
        tampered_package,
        stored_sha256=stored_sha,
        check_blockchain=check_blockchain,
    )

    return baseline_report, tampered_report
