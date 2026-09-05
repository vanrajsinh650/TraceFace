#!/usr/bin/env python3
"""
TraceFace — Face Discovery, Evidence Fusion & Cryptographic Ledger
===================================================================
HH Goa 2026 Task 3: Face Identification & Blockchain Verification

Usage:
    # Full Discovery & Anchoring Pipeline (LIVE MODE):
    python main.py --image path/to/face.jpg [--threshold 0.35] [--no-blockchain]

    # Public Blockchain Proof Verification (PROOF MODE):
    python main.py proof-verify fixtures/demo_evidence.json

    # Cryptographic Re-Verification:
    python main.py verify results/evidence_xxxx.json

    # Live Tamper Demonstration:
    python main.py tamper-demo results/evidence_xxxx.json

    # Candidate Inclusion Proof:
    python main.py proof results/evidence_xxxx.json
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

# Load .env if present
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from traceface.blockchain.client import BlockchainClient
from traceface.blockchain.verifier import reverify_file, run_tamper_demo
from traceface.evidence.filter import filter_candidate_image, rank_candidates_coarse
from traceface.evidence.fingerprint import compute_dual_fingerprint, compute_exact_sha256
from traceface.evidence.graph import build_investigation_graph
from traceface.evidence.merkle import MerkleInclusionProof, ProofStep
from traceface.evidence.models import CandidateEvidenceItem, MatchedCandidateEvidence
from traceface.evidence.package import (
    EvidencePackage,
    build_evidence_package,
    load_evidence_package,
    save_evidence_package,
)
from traceface.evidence.scoring import calculate_evidence_confidence
from traceface.face.detector import FaceDetector
from traceface.face.verifier import DEFAULT_THRESHOLD, FaceVerifier
from traceface.search.manager import SearchManager
from traceface.search.models import NormalizedCandidate, SearchMatch


# ─────────────────────────── CLI Display Helpers ────────────────────────────

def _step(n: int, total: int, msg: str) -> None:
    print(f"\n[{n}/{total}] {msg}")


def _ok(msg: str) -> None:
    print(f"  ✓ {msg}")


def _fail(msg: str) -> None:
    print(f"  ✗ {msg}", file=sys.stderr)


def _info(msg: str) -> None:
    print(f"  • {msg}")


def _header(msg: str) -> None:
    print(f"\n{'─' * 66}")
    print(f"  {msg}")
    print(f"{'─' * 66}")


def _download_image(url: str, timeout: int = 15) -> bytes | None:
    """Download an image from a URL. Returns bytes or None on failure."""
    try:
        import httpx
        headers = {"User-Agent": "TraceFace/2.0 (research/forensics)"}
        with httpx.Client(timeout=timeout, follow_redirects=True) as client:
            resp = client.get(url, headers=headers)
            resp.raise_for_status()
            content_type = resp.headers.get("content-type", "").lower()
            if "image" not in content_type and "octet" not in content_type:
                return None
            return resp.content
    except Exception:
        return None


# ─────────────────────────── Core Discovery Pipeline ────────────────────────

async def run_pipeline(
    image_path: str,
    threshold: float = DEFAULT_THRESHOLD,
    no_blockchain: bool = False,
    max_candidates: int = 10,
) -> None:
    TOTAL_STEPS = 7
    timings: dict[str, int] = {}
    pipeline_start = time.monotonic()

    input_path = Path(image_path)
    if not input_path.exists():
        _fail(f"Input image not found: {image_path}")
        sys.exit(1)

    query_image_bytes = input_path.read_bytes()
    investigation_id = f"inv_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}_{compute_exact_sha256(query_image_bytes)[:8]}"

    print(f"\nTraceFace — Cryptographic Face Discovery & Evidence Ledger")
    print(f"Investigation: {investigation_id}")
    print(f"Input image:   {input_path.name} ({len(query_image_bytes)//1024} KB)")

    # ── Step 1: Face Detection & ArcFace Embedding ─────────────────────────
    _step(1, TOTAL_STEPS, "Detecting face and computing ArcFace embedding...")
    t0 = time.monotonic()

    detector = FaceDetector(det_thresh=0.5)
    if not detector.available:
        _fail("InsightFace is unavailable. Install: pip install insightface onnxruntime")
        sys.exit(1)

    detection = detector.detect(query_image_bytes)
    det_time = time.monotonic() - t0
    timings["face_detection_ms"] = int(det_time * 1000)

    if not detection.success or not detection.faces:
        _fail(f"Face detection failed: {detection.error or 'No faces detected'}")
        sys.exit(1)

    _ok(f"Detected {len(detection.faces)} face(s) in {timings['face_detection_ms']} ms")
    query_face = detection.primary_face
    if not query_face or not query_face.embedding:
        _fail("Could not generate 512D ArcFace embedding.")
        sys.exit(1)

    # Dual fingerprint for query image
    t_fp = time.monotonic()
    query_fingerprint = compute_dual_fingerprint(query_image_bytes)
    timings["query_fingerprint_ms"] = int((time.monotonic() - t_fp) * 1000)

    _ok(f"Primary face bbox: {query_face.bbox} (conf: {query_face.confidence:.3f})")
    _ok(f"Embedding: 512-dim ArcFace unit vector")
    _ok(f"Exact SHA-256: {query_fingerprint.exact_sha256[:20]}...")
    if query_fingerprint.perceptual_hash:
        _ok(f"Perceptual dHash: {query_fingerprint.perceptual_hash} (alg: {query_fingerprint.perceptual_algorithm})")

    # ── Step 2: Parallel Search Fan-Out ────────────────────────────────────
    _step(2, TOTAL_STEPS, "Executing parallel multi-engine reverse search...")
    t_search = time.monotonic()

    search_manager = SearchManager()
    search_result = await search_manager.search(query_image_bytes)
    timings["search_total_ms"] = int((time.monotonic() - t_search) * 1000)

    # Print per-provider telemetry and failure isolation status
    for prov, p_exec in search_result.provider_runs.items():
        status_icon = "✓" if p_exec.status == "success" else ("○" if p_exec.status == "empty" else "✗")
        timings[f"provider_{prov}_ms"] = p_exec.latency_ms
        print(f"      {prov:<10} [{status_icon}] {p_exec.status:<8} ({p_exec.matches_count} matches, {p_exec.latency_ms} ms)")

    if not search_result.success or not search_result.candidates:
        _fail(f"Search discovery yielded no candidates: {search_result.error}")
        sys.exit(1)

    _ok(f"Discovered {len(search_result.candidates)} unique candidates across engines")

    # ── Step 3: Candidate Normalization, Ranking & Coarse Filtering ────────
    _step(3, TOTAL_STEPS, "Normalizing, deduplicating, and coarse-filtering candidates...")
    ranked_candidates = search_manager.prioritize_social(search_result.candidates)
    coarse_pool = rank_candidates_coarse(ranked_candidates, max_candidates=max_candidates)
    consensus_name = search_manager.best_person_name(ranked_candidates)

    if consensus_name:
        _ok(f"Consensus person name: {consensus_name}")

    # ── Step 4: Independent ArcFace Verification & Dual Fingerprinting ─────
    _step(4, TOTAL_STEPS, f"Independent face verification across top {len(coarse_pool)} candidates...")
    t_verif = time.monotonic()

    verifier = FaceVerifier(detector=detector, threshold=threshold)
    verified_items: list[CandidateEvidenceItem] = []
    matched_candidate_record: MatchedCandidateEvidence | None = None
    matched_image_bytes: bytes | None = None

    for cand in coarse_pool:
        # Download image
        img_bytes = _download_image(cand.image_url)
        filter_res = filter_candidate_image(img_bytes)

        if not filter_res.passed:
            verified_items.append(CandidateEvidenceItem(
                candidate_id=cand.candidate_id,
                canonical_url=cand.canonical_url,
                source_domain=cand.source_domain,
                image_url=cand.image_url,
                providers=cand.providers,
                verification_status="FILTER_REJECTED" if img_bytes else "DOWNLOAD_FAILED",
                title=cand.title,
                person_name=cand.person_name,
            ))
            continue

        # Dual fingerprint on candidate image
        cand_fp = compute_dual_fingerprint(img_bytes)

        # Deep multi-face ArcFace verification
        v_res = verifier.verify(query_face.embedding, img_bytes)

        # Calculate evidence confidence for this candidate
        cand_conf = calculate_evidence_confidence(
            face_similarity=v_res.best_score,
            threshold=threshold,
            margin=v_res.margin,
            candidate_faces_checked=v_res.candidate_faces_checked,
            providers=cand.providers,
            matched_url=cand.canonical_url,
            image_width=filter_res.width,
            image_height=filter_res.height,
        )

        item = CandidateEvidenceItem(
            candidate_id=cand.candidate_id,
            canonical_url=cand.canonical_url,
            source_domain=cand.source_domain,
            image_url=cand.image_url,
            providers=cand.providers,
            image_sha256=cand_fp.exact_sha256,
            perceptual_hash=cand_fp.perceptual_hash,
            perceptual_algorithm=cand_fp.perceptual_algorithm,
            face_similarity_score=v_res.best_score,
            runner_up_score=v_res.runner_up_score,
            margin=v_res.margin,
            candidate_faces_checked=v_res.candidate_faces_checked,
            verification_status="MATCH" if v_res.passed_threshold else "NO_MATCH",
            evidence_confidence=cand_conf.total_score,
            title=cand.title,
            person_name=cand.person_name or consensus_name,
        )
        verified_items.append(item)

        agreement_str = f"[{','.join(cand.providers)}]"
        if v_res.passed_threshold and matched_candidate_record is None:
            _ok(f"{cand.candidate_id} {agreement_str} {cand.source_domain}: MATCH (score {v_res.best_score:.4f} >= {threshold})")
            matched_image_bytes = img_bytes
            matched_candidate_record = MatchedCandidateEvidence(
                matched_candidate_id=cand.candidate_id,
                matched_source_url=cand.canonical_url,
                matched_image_url=cand.image_url,
                matched_image_sha256=cand_fp.exact_sha256,
                matched_image_perceptual_hash=cand_fp.perceptual_hash,
                matched_face_similarity=v_res.best_score,
                matched_verification_status="MATCH",
                source_domain=cand.source_domain,
                providers=cand.providers,
                evidence_confidence=cand_conf.total_score,
                person_name=cand.person_name or consensus_name,
            )
        else:
            status_text = "MATCH (secondary)" if v_res.passed_threshold else "NO_MATCH"
            print(f"      {cand.candidate_id} {agreement_str} {cand.source_domain}: {status_text} (score {v_res.best_score:.4f})")

    timings["verification_ms"] = int((time.monotonic() - t_verif) * 1000)

    if matched_candidate_record is None:
        _fail(f"No candidates satisfied ArcFace similarity threshold {threshold}")
        sys.exit(0)

    # ── Step 5: Multi-Signal Evidence Scoring & Evidence Graph ─────────────
    _step(5, TOTAL_STEPS, "Fusing evidence, computing confidence score, and building provenance graph...")
    t_graph = time.monotonic()

    final_score = calculate_evidence_confidence(
        face_similarity=matched_candidate_record.matched_face_similarity,
        threshold=threshold,
        margin=matched_candidate_record.matched_face_similarity - 0.15,
        candidate_faces_checked=1,
        providers=matched_candidate_record.providers,
        matched_url=matched_candidate_record.matched_source_url,
    )

    _ok(f"Evidence confidence: {final_score.total_score:.1f}/100 ({final_score.rating})")
    for comp in final_score.components:
        print(f"      • {comp.name:<20}: {comp.points:4.1f}/{comp.max_points:<2.0f} pts [{comp.assessment}]")

    evidence_graph = build_investigation_graph(
        investigation_id=investigation_id,
        query_image_sha=query_fingerprint.exact_sha256,
        query_face_bbox=query_face.bbox,
        query_face_conf=query_face.confidence,
        providers_run=search_result.provider_runs,
        candidates_data=[c.to_canonical_dict() for c in verified_items],
        matched_candidate_id=matched_candidate_record.matched_candidate_id,
        verification_data={
            "best_score": matched_candidate_record.matched_face_similarity,
            "threshold": threshold,
            "passed": True,
        },
        evidence_package_id=investigation_id,
    )
    timings["graph_build_ms"] = int((time.monotonic() - t_graph) * 1000)
    _ok(f"Evidence graph built: {len(evidence_graph.nodes)} nodes, {len(evidence_graph.edges)} edges")

    # ── Step 6: Cryptographic Merkle Evidence Tree & Inclusion Proof ────────
    _step(6, TOTAL_STEPS, "Constructing deterministic Merkle Evidence Tree...")
    t_merkle = time.monotonic()

    package = build_evidence_package(
        investigation_id=investigation_id,
        query_image_bytes=query_image_bytes,
        query_face_bbox=query_face.bbox,
        query_face_confidence=query_face.confidence,
        provider_runs=search_result.provider_runs,
        candidate_items=verified_items,
        matched_candidate=matched_candidate_record,
        confidence_score=final_score,
        evidence_graph=evidence_graph,
        timings_ms=timings,
    )
    timings["merkle_build_ms"] = int((time.monotonic() - t_merkle) * 1000)

    evidence_sha256 = package.sha256()
    _ok(f"Merkle Evidence Root: {package.merkle_root}")
    _ok(f"Merkle Tree leaves:   {package.merkle_leaf_count}")
    _ok(f"Evidence SHA-256:     {evidence_sha256}")

    # Demonstrate inclusion proof verification
    if package.matched_inclusion_proof:
        steps = [
            ProofStep(sibling_hash=s["sibling_hash"], position=s["position"])
            for s in package.matched_inclusion_proof.get("audit_path", [])
        ]
        proof = MerkleInclusionProof(
            leaf_id=package.matched_inclusion_proof["leaf_id"],
            leaf_hash=package.matched_inclusion_proof["leaf_hash"],
            merkle_root=package.merkle_root,
            leaf_index=package.matched_inclusion_proof["leaf_index"],
            audit_path=steps,
        )
        if proof.verify():
            _ok(f"Merkle Inclusion Proof verified for {proof.leaf_id} (path depth: {len(steps)})")

    # Save evidence file locally
    evidence_path = save_evidence_package(package, evidence_sha256)
    _ok(f"Evidence package persisted: {evidence_path}")

    # ── Step 7: Blockchain Anchoring & Integrity Verification ───────────────
    _step(7, TOTAL_STEPS, "Anchoring Merkle Root & Discovered Post Fingerprint to Ethereum Sepolia...")
    t_bc = time.monotonic()

    print(f"  • Matched Post URL:    {matched_candidate_record.matched_source_url}")
    print(f"  • Post Image SHA-256:  {matched_candidate_record.matched_image_sha256}")
    if matched_candidate_record.matched_image_perceptual_hash:
        print(f"  • Post Image dHash:    {matched_candidate_record.matched_image_perceptual_hash}")
    print(f"  • Evidence Leaf ID:    {matched_candidate_record.matched_candidate_id} (locked inside Merkle Root)")
    print(f"  • Committed Root:      {package.merkle_root}")

    tx_hash = ""
    block_num = 0
    blockchain_status = "SKIPPED"

    if no_blockchain:
        print("  • Blockchain anchoring skipped via --no-blockchain (Local ledger committed)")
        blockchain_status = "SKIPPED (--no-blockchain)"
    else:
        client = BlockchainClient()
        wallet = client.get_wallet_address()
        if not wallet or not client.is_configured:
            _fail("Ethereum Sepolia configuration missing or incomplete (.env)")
            blockchain_status = "CONFIG_MISSING (Check .env for SEPOLIA_RPC_URL, PRIVATE_KEY, CONTRACT_ADDRESS)"
        else:
            _ok(f"Deployer Wallet: {wallet}")
            metadata = {
                "investigation_id": investigation_id,
                "merkle_root": package.merkle_root,
                "evidence_sha256": evidence_sha256,
                "matched_candidate_id": matched_candidate_record.matched_candidate_id,
                "matched_post_url": matched_candidate_record.matched_source_url,
                "matched_post_fingerprint": matched_candidate_record.matched_image_sha256,
                "matched_post_perceptual_hash": matched_candidate_record.matched_image_perceptual_hash,
                "matched_face_similarity": round(matched_candidate_record.matched_face_similarity, 4),
                "confidence": round(final_score.total_score, 2),
                "timestamp": package.created_at,
            }

            print("  • Submitting Merkle root transaction to Ethereum Sepolia...")
            anchor = client.anchor(package.merkle_root, metadata)

            if anchor.success:
                tx_hash = anchor.tx_hash
                block_num = anchor.block_number
                _ok(f"Transaction: {tx_hash}")
                _ok(f"Confirmed in block: {block_num}")
                _ok(f"Explorer: {anchor.explorer_url()}")

                # Immediate on-chain verification
                print("  • Re-verifying anchored Merkle root against smart contract...")
                bc_verify = client.verify(package.merkle_root)
                if bc_verify.verified:
                    _ok(f"On-chain root: {bc_verify.stored_hash}")
                    _ok(f"Blockchain verification: VERIFIED")
                    blockchain_status = "ANCHORED & VERIFIED"
                else:
                    _fail(f"Blockchain verification: {bc_verify.status}")
                    blockchain_status = bc_verify.status
            else:
                _fail(f"Anchor submission failed: {anchor.error}")
                blockchain_status = f"ANCHOR_FAILED: {anchor.error}"

    timings["blockchain_ms"] = int((time.monotonic() - t_bc) * 1000)
    timings["total_pipeline_ms"] = int((time.monotonic() - pipeline_start) * 1000)

    # ── Final Summary ───────────────────────────────────────────────────────
    _header("TRACEFACE INVESTIGATION & EVIDENCE SUMMARY")
    print(f"  Investigation ID:    {investigation_id}")
    print(f"  Matched Candidate:   {matched_candidate_record.matched_candidate_id}")
    print(f"  Source Platform:     {matched_candidate_record.source_domain}")
    print(f"  Discovered Post URL: {matched_candidate_record.matched_source_url}")
    print(f"  Post Image SHA-256:  {matched_candidate_record.matched_image_sha256}")
    if matched_candidate_record.matched_image_perceptual_hash:
        print(f"  Post Image dHash:    {matched_candidate_record.matched_image_perceptual_hash}")
    if matched_candidate_record.person_name:
        print(f"  Consensus Identity:  {matched_candidate_record.person_name}")
    print(f"  Face Similarity:     {matched_candidate_record.matched_face_similarity:.4f} (threshold: {threshold})")
    print(f"  Provider Agreement:  {', '.join(matched_candidate_record.providers)} ({len(matched_candidate_record.providers)} engine(s))")
    print(f"  Evidence Confidence: {final_score.total_score:.1f}/100 [{final_score.rating}]")
    print(f"  Query Exact SHA-256: {query_fingerprint.exact_sha256}")
    print(f"  Query dHash:         {query_fingerprint.perceptual_hash}")
    print(f"  Merkle Evidence Root:{package.merkle_root}")
    print(f"  Evidence File:       {evidence_path}")
    if tx_hash:
        print(f"  Ethereum Sepolia Tx: {tx_hash}")
        print(f"  Block Number:        {block_num}")
    print(f"  Blockchain Status:   {blockchain_status}")

    _header("STAGE PERFORMANCE & LATENCY OBSERVABILITY")
    print(f"  Face Detection:          {timings.get('face_detection_ms', 0):>5} ms")
    print(f"  Multi-Engine Search:     {timings.get('search_total_ms', 0):>5} ms")
    print(f"  Candidate Verification:  {timings.get('verification_ms', 0):>5} ms")
    print(f"  Evidence Graph:          {timings.get('graph_build_ms', 0):>5} ms")
    print(f"  Merkle Tree Build:       {timings.get('merkle_build_ms', 0):>5} ms")
    if not no_blockchain:
        print(f"  Blockchain Anchor/Check: {timings.get('blockchain_ms', 0):>5} ms")
    print(f"  Total Pipeline Latency:  {timings.get('total_pipeline_ms', 0):>5} ms")
    print(f"{'─' * 66}\n")


# ─────────────────────────── Verification & Tamper Commands ─────────────────

def cmd_verify(file_path: str) -> None:
    """Execute complete cryptographic verification of an evidence file."""
    _header("TRACEFACE CRYPTOGRAPHIC RE-VERIFICATION")
    print(f"Target Evidence: {file_path}")

    report = reverify_file(file_path, check_blockchain=True)

    print(f"\nInvestigation:     {report.investigation_id}")
    print(f"Stored Root:       {report.stored_merkle_root}")
    print(f"Recomputed Root:   {report.recomputed_merkle_root}")
    if report.on_chain_root:
        print(f"On-Chain Root:     {report.on_chain_root}")
    print(f"Root Match:        {'✓ MATCH' if report.root_match else '✗ MISMATCH'}")
    print(f"Evidence SHA-256:  {'✓ MATCH' if report.sha256_match else '✗ MISMATCH'}")
    print(f"Inclusion Proof:   {'✓ VALID' if report.inclusion_proof_valid else '✗ INVALID'}")

    if report.blockchain_anchored:
        print(f"On-Chain Anchor:   ✓ FOUND ON ETHEREUM SEPOLIA ({report.on_chain_root})")
    elif report.blockchain_error:
        print(f"On-Chain Anchor:   ○ {report.blockchain_error}")

    print(f"\nVerification Result:")
    if report.is_valid:
        print("  ✅ VERIFIED — All cryptographic commitments authenticate successfully.")
    else:
        print("  ❌ TAMPERED — Evidence does not match cryptographic root.")
        for detail in report.tamper_details:
            print(f"     • {detail}")
    print(f"{'─' * 66}\n")


def cmd_tamper_demo(file_path: str) -> None:
    """Demonstrate tamper-detection by mutating in-memory evidence."""
    _header("TRACEFACE TAMPER-RESISTANCE DEMONSTRATION")
    print(f"Target Evidence: {file_path}")
    print("Executing non-destructive in-memory mutation test...\n")

    baseline, tampered = run_tamper_demo(file_path, tamper_field="similarity")

    print("[Phase 1] Untouched Original Verification:")
    print(f"  Stored Root:      {baseline.stored_merkle_root[:24]}...")
    print(f"  Recomputed Root:  {baseline.recomputed_merkle_root[:24]}...")
    print(f"  Result:           {'✅ VERIFIED' if baseline.is_valid else '❌ TAMPERED'}")

    print("\n[Phase 2] Controlled Modification (similarity score altered in copy):")
    print(f"  Original Root:    {tampered.stored_merkle_root[:24]}...")
    print(f"  Tampered Root:    {tampered.recomputed_merkle_root[:24]}...")
    print(f"  Root Match:       {'✓ MATCH' if tampered.root_match else '✗ MISMATCH'}")
    print(f"  Result:           {'✅ VERIFIED' if tampered.is_valid else '❌ TAMPERED'}")
    for d in tampered.tamper_details:
        print(f"  Reason:           {d}")

    print("\n[Phase 3] Re-verifying Original Disk File:")
    re_check = reverify_file(file_path, check_blockchain=False)
    print(f"  Disk File Status: {'✅ VERIFIED (File is completely intact)' if re_check.is_valid else '❌ TAMPERED'}")
    print(f"{'─' * 66}\n")


def cmd_proof(file_path: str) -> None:
    """Inspect and verify cryptographic Merkle inclusion proof."""
    _header("TRACEFACE MERKLE INCLUSION PROOF")
    package, _ = load_evidence_package(file_path)

    if not package.matched_inclusion_proof:
        print("No inclusion proof found in evidence package.")
        return

    proof_data = package.matched_inclusion_proof
    leaf_id = proof_data["leaf_id"]
    leaf_hash = proof_data["leaf_hash"]
    root = proof_data["merkle_root"]
    audit_path = proof_data["audit_path"]

    print(f"Evidence Leaf ID:   {leaf_id}")
    print(f"Leaf Hash (SHA256): {leaf_hash}")
    print(f"Committed Root:     {root}")
    print(f"Audit Path Steps:   {len(audit_path)}")

    for idx, step in enumerate(audit_path, start=1):
        print(f"  Step {idx}: {step['position']:<5} sibling = {step['sibling_hash']}")

    steps = [ProofStep(s["sibling_hash"], s["position"]) for s in audit_path]
    proof = MerkleInclusionProof(
        leaf_id=leaf_id,
        leaf_hash=leaf_hash,
        merkle_root=root,
        leaf_index=proof_data["leaf_index"],
        audit_path=steps,
    )

    valid = proof.verify()
    print(f"\nProof Cryptographic Verification:")
    if valid:
        print("  ✅ INCLUSION PROVEN: Candidate is mathematically locked into the Merkle Root.")
    else:
        print("  ❌ INCLUSION FAILED: Path does not compute to committed Merkle Root.")
    print(f"{'─' * 66}\n")


def cmd_proof_verify(file_path: str) -> None:
    """Verify a public proof fixture against Ethereum Sepolia (read-only, no wallet required)."""
    _header("TRACEFACE PUBLIC PROOF VERIFICATION")
    print(f"Evidence file: {file_path}\n")

    # 1. Load raw JSON to extract proof metadata
    raw_file = Path(file_path)
    if not raw_file.exists():
        _fail(f"File not found: {file_path}")
        return
    raw_data = json.loads(raw_file.read_text())
    proof_meta = raw_data.get("_proof_metadata", {})

    if proof_meta:
        print(f"Network:       {proof_meta.get('network', 'unknown')}")
        print(f"Chain ID:      {proof_meta.get('chain_id', 'unknown')}")
        print(f"Contract:      {proof_meta.get('contract_address', 'unknown')}")
        print(f"Anchor TX:     {proof_meta.get('anchor_tx', 'unknown')}")
        print(f"Block:         {proof_meta.get('block_number', 'unknown')}")
        print(f"Verification:  {proof_meta.get('verification_mode', 'unknown')}")
        print()

    # 2. Load evidence package via standard loader
    package, pkg_raw = load_evidence_package(file_path)
    stored_sha256 = raw_data.get("evidence_sha256", "")
    stored_root = raw_data.get("merkle_root", package.merkle_root)

    # 3. Recompute evidence SHA-256
    recomputed_sha = package.sha256()
    sha_match = recomputed_sha == stored_sha256

    # 4. Recompute Merkle root
    recomputed_result = package.recompute_merkle_root()
    recomputed_root = recomputed_result[0] if isinstance(recomputed_result, tuple) else recomputed_result
    root_match = recomputed_root == stored_root

    # 5. Verify inclusion proof
    inclusion_valid = False
    if package.matched_inclusion_proof:
        proof_data = package.matched_inclusion_proof
        steps = [ProofStep(s["sibling_hash"], s["position"]) for s in proof_data["audit_path"]]
        proof = MerkleInclusionProof(
            leaf_id=proof_data["leaf_id"],
            leaf_hash=proof_data["leaf_hash"],
            merkle_root=recomputed_root,
            leaf_index=proof_data["leaf_index"],
            audit_path=steps,
        )
        inclusion_valid = proof.verify()

    # 6. Query Ethereum Sepolia (read-only — no PRIVATE_KEY needed)
    on_chain_root = None
    blockchain_found = False
    blockchain_error = None
    contract_addr = proof_meta.get("contract_address", os.environ.get("CONTRACT_ADDRESS", ""))
    try:
        client = BlockchainClient(contract_address=contract_addr)
        result = client.verify(recomputed_root)
        if result.verified:
            blockchain_found = True
            on_chain_root = f"0x{recomputed_root}"
    except Exception as e:
        blockchain_error = str(e)

    # 7. Print results
    print(f"Stored Merkle Root:     {stored_root}")
    print(f"Recomputed Merkle Root: {recomputed_root}")
    if on_chain_root:
        print(f"On-Chain Merkle Root:   {on_chain_root}")
    print(f"Evidence SHA-256:       {'MATCH' if sha_match else 'MISMATCH'}")
    print(f"Merkle Root:            {'MATCH' if root_match else 'MISMATCH'}")
    print(f"Merkle Inclusion Proof: {'VALID' if inclusion_valid else 'INVALID'}")

    if blockchain_found:
        print(f"On-Chain Commitment:    FOUND")
    elif blockchain_error:
        print(f"On-Chain Commitment:    UNAVAILABLE ({blockchain_error})")
    else:
        print(f"On-Chain Commitment:    NOT FOUND")

    # 8. Final verdict
    all_crypto_valid = sha_match and root_match and inclusion_valid
    print(f"\nFinal Result:")
    if all_crypto_valid and blockchain_found:
        print("  ✅ VERIFIED — PUBLIC PROOF AUTHENTICATED")
        print("     All cryptographic commitments recomputed and verified on Ethereum Sepolia.")
    elif all_crypto_valid:
        print("  ⚠️  CRYPTOGRAPHICALLY VALID — blockchain access unavailable")
        print("     All local cryptographic checks passed but on-chain verification could not be performed.")
    else:
        print("  ❌ VERIFICATION FAILED")
        if not sha_match:
            print("     Evidence SHA-256 does not match.")
        if not root_match:
            print("     Merkle root does not match.")
        if not inclusion_valid:
            print("     Inclusion proof is invalid.")
    print(f"{'─' * 66}\n")


# ─────────────────────────── CLI Entrypoint ─────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="TraceFace — Cryptographic Face Discovery & Evidence Ledger"
    )
    # Pipeline execution
    parser.add_argument("--image", help="Path to input face image to run full discovery pipeline")
    parser.add_argument(
        "--threshold",
        type=float,
        default=DEFAULT_THRESHOLD,
        help=f"Cosine similarity threshold (default: {DEFAULT_THRESHOLD})"
    )
    parser.add_argument(
        "--no-blockchain",
        action="store_true",
        help="Skip Ethereum Sepolia blockchain anchoring"
    )
    parser.add_argument(
        "--max-candidates",
        type=int,
        default=10,
        help="Max number of search candidates to verify (default: 10)"
    )

    # Subcommands
    subparsers = parser.add_subparsers(dest="command", help="TraceFace Subcommands")

    verify_parser = subparsers.add_parser("verify", help="Re-verify evidence file against Merkle root")
    verify_parser.add_argument("evidence_file", help="Path to results/evidence_xxxx.json")

    tamper_parser = subparsers.add_parser("tamper-demo", help="Demonstrate live tamper detection")
    tamper_parser.add_argument("evidence_file", help="Path to results/evidence_xxxx.json")

    proof_parser = subparsers.add_parser("proof", help="Inspect and verify Merkle inclusion proof")
    proof_parser.add_argument("evidence_file", help="Path to results/evidence_xxxx.json")

    proof_verify_parser = subparsers.add_parser(
        "proof-verify",
        help="Verify a public proof fixture against Ethereum Sepolia (read-only, no wallet required)"
    )
    proof_verify_parser.add_argument("evidence_file", help="Path to fixtures/demo_evidence.json")

    args = parser.parse_args()

    if args.command == "verify":
        cmd_verify(args.evidence_file)
    elif args.command == "tamper-demo":
        cmd_tamper_demo(args.evidence_file)
    elif args.command == "proof":
        cmd_proof(args.evidence_file)
    elif args.command == "proof-verify":
        cmd_proof_verify(args.evidence_file)
    elif args.image:
        asyncio.run(run_pipeline(
            image_path=args.image,
            threshold=args.threshold,
            no_blockchain=args.no_blockchain,
            max_candidates=args.max_candidates,
        ))
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
