#!/usr/bin/env python3
"""
TraceFace — Main CLI
=====================
HH Goa 2026 Task 3: Face Identification & Blockchain Verification

Usage:
    python main.py --image path/to/face.jpg [--threshold 0.35] [--no-blockchain]

Pipeline:
    [1/7] Face detection + ArcFace embedding
    [2/7] Reverse image / web search
    [3/7] Candidate URL filtering & image download
    [4/7] Independent face verification (query vs ALL candidate faces)
    [5/7] Evidence package creation
    [6/7] SHA-256 hash
    [7/7] Blockchain anchor + verification (Polygon Amoy)
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path
from urllib.parse import urlparse

# Load .env if available
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from traceface.face.detector import FaceDetector
from traceface.face.verifier import FaceVerifier, DEFAULT_THRESHOLD
from traceface.search.manager import SearchManager
from traceface.search.models import SearchMatch
from traceface.evidence.package import create_evidence_package, save_evidence_package
from traceface.blockchain.client import BlockchainClient


# ─────────────────────────── CLI helpers ────────────────────────────────────

def _step(n: int, total: int, msg: str) -> None:
    print(f"\n[{n}/{total}] {msg}")


def _ok(msg: str) -> None:
    print(f"  ✓ {msg}")


def _fail(msg: str) -> None:
    print(f"  ✗ {msg}", file=sys.stderr)


def _header(msg: str) -> None:
    print(f"\n{'─' * 60}")
    print(f"  {msg}")
    print(f"{'─' * 60}")


# ─────────────────────────── Candidate image download ───────────────────────

def _download_image(url: str, timeout: int = 15) -> bytes | None:
    """Download an image from a URL. Returns bytes or None on failure."""
    try:
        import httpx
        headers = {"User-Agent": "TraceFace/1.0 (research/academic)"}
        with httpx.Client(timeout=timeout, follow_redirects=True) as client:
            resp = client.get(url, headers=headers)
            resp.raise_for_status()
            content_type = resp.headers.get("content-type", "")
            if "image" not in content_type and "octet" not in content_type:
                # Not an image — this is a web page, not a direct image URL
                return None
            return resp.content
    except Exception as e:
        print(f"  [download] Failed {url[:60]}... → {e}")
        return None


def _find_candidate_image_url(match: SearchMatch) -> str:
    """
    Get the best image URL to download from a search match.
    Prefer thumbnail_url if it's a direct image, otherwise use the main URL.
    """
    if match.thumbnail_url:
        return match.thumbnail_url
    return match.url


# ─────────────────────────── Main pipeline ──────────────────────────────────

async def run_pipeline(
    image_path: str,
    threshold: float = DEFAULT_THRESHOLD,
    no_blockchain: bool = False,
    max_candidates: int = 10,
) -> None:
    """
    Full TraceFace pipeline:
    face detect → search → verify → evidence → hash → blockchain → verify
    """
    TOTAL_STEPS = 7

    # ── Load input image ────────────────────────────────────────────────────
    input_path = Path(image_path)
    if not input_path.exists():
        print(f"ERROR: Input image not found: {image_path}", file=sys.stderr)
        sys.exit(1)

    query_image_bytes = input_path.read_bytes()
    print(f"\nTraceFace — Face Identification & Blockchain Verification")
    print(f"Input: {input_path.name} ({len(query_image_bytes)//1024}KB)")

    # ── Step 1: Face Detection ───────────────────────────────────────────────
    _step(1, TOTAL_STEPS, "Face Detection + ArcFace Embedding")

    detector = FaceDetector(det_thresh=0.5)
    if not detector.available:
        _fail("InsightFace not available. Install: pip install insightface onnxruntime")
        sys.exit(1)

    detection = detector.detect(query_image_bytes)
    if not detection.success:
        _fail(f"Face detection failed: {detection.error}")
        sys.exit(1)

    if not detection.faces:
        _fail("No faces detected in input image.")
        sys.exit(1)

    _ok(f"Detected {len(detection.faces)} face(s)")

    query_face = detection.primary_face
    if not query_face or not query_face.embedding:
        _fail("Could not extract embedding from query face.")
        sys.exit(1)

    _ok(f"Query face: bbox={query_face.bbox}, confidence={query_face.confidence:.3f}")
    _ok(f"Embedding: {len(query_face.embedding)}-dim ArcFace vector")

    # ── Step 2: Reverse Image Search ────────────────────────────────────────
    _step(2, TOTAL_STEPS, "Reverse Image / Web Search")

    search_manager = SearchManager()
    search_result = await search_manager.search(query_image_bytes)

    if not search_result.success or not search_result.matches:
        _fail(f"Search failed: {search_result.error or 'No matches found'}")
        print("\nSEARCH FAILED")
        print(f"Provider: {search_result.provider}")
        print(f"Reason: {search_result.error or 'No results returned'}")
        sys.exit(1)

    _ok(f"Found {len(search_result.matches)} candidate URLs (provider: {search_result.provider})")

    # Prioritize social domains
    ranked_matches = search_manager.prioritize_social(search_result.matches)
    person_name_guess = search_manager.best_person_name(search_result)
    if person_name_guess:
        _ok(f"Likely person: {person_name_guess}")

    # ── Step 3: Candidate Filtering & Download ───────────────────────────────
    _step(3, TOTAL_STEPS, "Candidate Filtering & Image Download")

    verifier = FaceVerifier(detector=detector, threshold=threshold)
    verified_match: SearchMatch | None = None
    verified_image_bytes: bytes | None = None
    verified_result = None

    candidates_tried = 0

    for match in ranked_matches[:max_candidates]:
        candidates_tried += 1
        domain = urlparse(match.url).netloc
        img_url = _find_candidate_image_url(match)

        print(f"  Trying [{candidates_tried}]: {domain} — {match.url[:70]}...")

        img_bytes = _download_image(img_url)
        if img_bytes is None:
            print(f"    → Could not download image, skipping")
            continue

        print(f"    → Downloaded {len(img_bytes)//1024}KB from {img_url[:60]}")

        # ── Step 4: Independent Face Verification ───────────────────────────
        _step(4, TOTAL_STEPS, f"Independent Face Verification (candidate {candidates_tried})")

        verify = verifier.verify(query_face.embedding, img_bytes)

        if verify.error:
            print(f"  Verification error: {verify.error}")
            continue

        print(f"  Candidate faces detected: {verify.candidate_faces_checked}")
        print(f"  Best similarity score: {verify.best_score:.4f} (threshold: {threshold})")
        if verify.runner_up_score is not None:
            print(f"  Runner-up score: {verify.runner_up_score:.4f} | Margin: {verify.margin:.4f}")

        if verify.passed_threshold:
            _ok(f"MATCH — score {verify.best_score:.4f} >= threshold {threshold}")
            verified_match = match
            verified_image_bytes = img_bytes
            verified_result = verify
            break
        else:
            print(f"  → No match (score {verify.best_score:.4f} < threshold {threshold})")

    if verified_match is None:
        print(f"\n{'─' * 60}")
        print("NO MATCH FOUND")
        print(f"Candidates tried: {candidates_tried}")
        print(f"Threshold: {threshold}")
        print("None of the search results matched the query face.")
        sys.exit(0)

    # ── Step 5: Evidence Package ─────────────────────────────────────────────
    _step(5, TOTAL_STEPS, "Creating Evidence Package")

    img_url = _find_candidate_image_url(verified_match)
    package = create_evidence_package(
        query_image_bytes=query_image_bytes,
        matched_url=verified_match.url,
        matched_image_url=img_url,
        search_provider=verified_match.source,
        face_similarity_score=verified_result.best_score,
        candidate_faces_checked=verified_result.candidate_faces_checked,
        similarity_threshold=threshold,
        model_name="buffalo_l",
        person_name=verified_match.person_name or person_name_guess,
        runner_up_score=verified_result.runner_up_score,
        margin=verified_result.margin,
    )

    _ok(f"Evidence package created")
    _ok(f"Source domain: {package.source_domain}")
    _ok(f"Search provider: {package.search_provider}")
    _ok(f"Timestamp: {package.timestamp_utc}")

    # ── Step 6: SHA-256 Hash ─────────────────────────────────────────────────
    _step(6, TOTAL_STEPS, "Computing SHA-256 Hash")

    evidence_hash = package.sha256()
    _ok(f"Evidence SHA-256: {evidence_hash}")

    # Save evidence file locally
    evidence_file = save_evidence_package(package, evidence_hash)
    _ok(f"Evidence saved: {evidence_file}")

    # ── Step 7: Blockchain Anchor + Verify ───────────────────────────────────
    _step(7, TOTAL_STEPS, "Blockchain Anchor (Polygon Amoy)")

    tx_hash = ""
    block_number = 0
    verified_on_chain = False
    blockchain_status = "SKIPPED"

    if no_blockchain:
        print("  Blockchain skipped (--no-blockchain)")
        blockchain_status = "SKIPPED (--no-blockchain)"
    else:
        client = BlockchainClient()
        wallet = client.get_wallet_address()

        if wallet:
            _ok(f"Wallet: {wallet}")
        else:
            _fail("Blockchain config incomplete. Set POLYGON_RPC_URL, PRIVATE_KEY, CONTRACT_ADDRESS in .env")
            blockchain_status = "CONFIG_MISSING"

        if wallet:
            # Anchor
            metadata = {
                "source_domain": package.source_domain,
                "search_provider": package.search_provider,
                "face_score": round(package.face_similarity_score, 6),
                "timestamp": package.timestamp_utc,
                "model": package.model_name,
            }

            print("  Anchoring hash on Polygon Amoy...")
            anchor = client.anchor(evidence_hash, metadata)

            if anchor.success:
                tx_hash = anchor.tx_hash
                block_number = anchor.block_number
                _ok(f"Anchored! Tx: {tx_hash}")
                _ok(f"Block: {block_number}")
                _ok(f"Explorer: {client.get_explorer_url(tx_hash)}")

                # Verify
                print("  Verifying against blockchain...")
                verify_bc = client.verify(evidence_hash)
                verified_on_chain = verify_bc.verified
                blockchain_status = verify_bc.status

                if verified_on_chain:
                    _ok(f"Blockchain verification: {blockchain_status}")
                else:
                    _fail(f"Blockchain verification: {blockchain_status}")
            else:
                _fail(f"Anchor failed: {anchor.error}")
                blockchain_status = f"ANCHOR_FAILED: {anchor.error}"

    # ── Final Output ─────────────────────────────────────────────────────────
    _header("TRACEFACE RESULT")
    print(f"  Status:            MATCH")
    print(f"  Source:            {package.source_domain}")
    print(f"  URL:               {package.matched_url}")
    if package.person_name:
        print(f"  Name (inferred):   {package.person_name}")
    print(f"  Face score:        {package.face_similarity_score:.4f} (threshold: {threshold})")
    print(f"  Faces checked:     {package.candidate_faces_checked}")
    if package.runner_up_score is not None:
        print(f"  Runner-up score:   {package.runner_up_score:.4f} | Margin: {package.margin:.4f}")
    print(f"  Search provider:   {package.search_provider}")
    print(f"  Model:             {package.model_name}")
    print(f"  Timestamp (UTC):   {package.timestamp_utc}")
    print(f"  Evidence SHA-256:  {evidence_hash}")
    print(f"  Evidence file:     {evidence_file}")
    if tx_hash:
        print(f"  Transaction:       {tx_hash}")
        print(f"  Block:             {block_number}")
    print(f"  Blockchain:        {blockchain_status}")
    print(f"{'─' * 60}\n")


# ─────────────────────────── Entrypoint ─────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="TraceFace — Face Identification & Blockchain Verification"
    )
    parser.add_argument("--image", required=True, help="Path to input face image")
    parser.add_argument(
        "--threshold",
        type=float,
        default=DEFAULT_THRESHOLD,
        help=f"Cosine similarity threshold for face match (default: {DEFAULT_THRESHOLD})"
    )
    parser.add_argument(
        "--no-blockchain",
        action="store_true",
        help="Skip blockchain anchoring (useful for testing)"
    )
    parser.add_argument(
        "--max-candidates",
        type=int,
        default=10,
        help="Max number of search candidates to verify (default: 10)"
    )

    args = parser.parse_args()

    asyncio.run(run_pipeline(
        image_path=args.image,
        threshold=args.threshold,
        no_blockchain=args.no_blockchain,
        max_candidates=args.max_candidates,
    ))


if __name__ == "__main__":
    main()
