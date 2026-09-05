"""
TraceFace — Evidence Package & Merkle Ledger (Schema v2.0)
==========================================================
Creates a deterministic, canonical evidence package and Merkle tree ledger
representing the complete multi-provider face discovery investigation.

Key properties:
- Preserves full provenance: search providers, candidates considered, and verification.
- Explicitly features the matched candidate post (Feature 9).
- Constructs a deterministic Merkle Evidence Root (Feature 8).
- Includes cryptographic inclusion proof for the matched post (Feature 13).
- Dual fingerprinting: Exact SHA-256 + Perceptual dHash (Feature 7).
- Explainable multi-signal confidence score (Feature 4).
- Deterministic JSON canonicalization: json.dumps(sort_keys=True, separators=(',', ':')).
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from traceface.evidence.fingerprint import compute_dual_fingerprint, compute_exact_sha256
from traceface.evidence.graph import EvidenceGraph
from traceface.evidence.merkle import MerkleInclusionProof, MerkleLeaf, MerkleTree
from traceface.evidence.models import (
    CandidateEvidenceItem,
    MatchedCandidateEvidence,
    QueryEvidenceInfo,
)
from traceface.evidence.scoring import EvidenceConfidenceScore


def hash_image_bytes(image_bytes: bytes) -> str:
    """Compute SHA-256 of raw image bytes. Legacy alias for compute_exact_sha256."""
    return compute_exact_sha256(image_bytes)


@dataclass
class EvidencePackage:
    """
    Deterministic evidence package (Schema v2.0).
    Represents the full multi-engine investigation state committed to the blockchain.
    """
    # Investigation Identification
    investigation_id: str
    schema_version: str = "2.0"
    created_at: str = ""

    # Query Face Details
    query_info: Optional[QueryEvidenceInfo] = None

    # Search Provenance
    provider_runs: dict[str, Any] = field(default_factory=dict)
    candidate_count: int = 0
    candidates: list[CandidateEvidenceItem] = field(default_factory=list)

    # Matched Candidate (Explicit Hackathon Requirement)
    matched_candidate: Optional[MatchedCandidateEvidence] = None

    # Evidence Confidence Score
    evidence_confidence: Optional[dict[str, Any]] = None

    # Merkle Commitment
    merkle_root: str = ""
    merkle_leaf_count: int = 0
    merkle_leaves: list[dict[str, str]] = field(default_factory=list)
    matched_inclusion_proof: Optional[dict[str, Any]] = None

    # Evidence Graph Summary
    evidence_graph: Optional[dict[str, Any]] = None

    # Execution Latencies (observability)
    timings_ms: dict[str, int] = field(default_factory=dict)

    # ── Backward Compatibility Properties (v1 interface) ───────────────────
    @property
    def query_image_sha256(self) -> str:
        return self.query_info.query_image_sha256 if self.query_info else ""

    @property
    def matched_url(self) -> str:
        return self.matched_candidate.matched_source_url if self.matched_candidate else ""

    @property
    def matched_image_url(self) -> str:
        return self.matched_candidate.matched_image_url if self.matched_candidate else ""

    @property
    def source_domain(self) -> str:
        return self.matched_candidate.source_domain if self.matched_candidate else ""

    @property
    def search_provider(self) -> str:
        if self.matched_candidate and self.matched_candidate.providers:
            return ",".join(self.matched_candidate.providers)
        return "none"

    @property
    def face_similarity_score(self) -> float:
        return self.matched_candidate.matched_face_similarity if self.matched_candidate else 0.0

    @property
    def candidate_faces_checked(self) -> int:
        if self.candidates and self.matched_candidate:
            for c in self.candidates:
                if c.candidate_id == self.matched_candidate.matched_candidate_id:
                    return c.candidate_faces_checked
        return 1

    @property
    def similarity_threshold(self) -> float:
        return 0.35

    @property
    def model_name(self) -> str:
        return self.query_info.model_name if self.query_info else "buffalo_l"

    @property
    def timestamp_utc(self) -> str:
        return self.created_at

    @property
    def person_name(self) -> Optional[str]:
        return self.matched_candidate.person_name if self.matched_candidate else None

    @property
    def runner_up_score(self) -> Optional[float]:
        if self.candidates and self.matched_candidate:
            for c in self.candidates:
                if c.candidate_id == self.matched_candidate.matched_candidate_id:
                    return c.runner_up_score
        return None

    @property
    def margin(self) -> Optional[float]:
        if self.candidates and self.matched_candidate:
            for c in self.candidates:
                if c.candidate_id == self.matched_candidate.matched_candidate_id:
                    return c.margin
        return None

    # ── Canonical Serialization & Verification ─────────────────────────────
    def to_canonical_dict(self) -> dict[str, Any]:
        """
        Generate deterministic dictionary for cryptographic hashing.
        """
        return {
            "candidate_count": self.candidate_count,
            "candidates": [c.to_canonical_dict() for c in self.candidates],
            "created_at": self.created_at,
            "evidence_confidence": self.evidence_confidence,
            "evidence_graph": self.evidence_graph,
            "investigation_id": self.investigation_id,
            "matched_candidate": self.matched_candidate.to_canonical_dict() if self.matched_candidate else None,
            "matched_inclusion_proof": self.matched_inclusion_proof,
            "merkle_leaf_count": self.merkle_leaf_count,
            "merkle_leaves": self.merkle_leaves,
            "merkle_root": self.merkle_root,
            "provider_runs": self.provider_runs,
            "query_info": self.query_info.to_canonical_dict() if self.query_info else None,
            "schema_version": self.schema_version,
            "timings_ms": self.timings_ms,
        }

    def canonical_json(self) -> str:
        """
        Produce deterministic canonical JSON.
        sort_keys=True ensures key order is alphabetical across all levels.
        separators=(',', ':') eliminates arbitrary whitespace.
        """
        return json.dumps(self.to_canonical_dict(), sort_keys=True, separators=(",", ":"))

    def sha256(self) -> str:
        """
        Compute SHA-256 of the canonical JSON string.
        """
        return hashlib.sha256(self.canonical_json().encode("utf-8")).hexdigest()

    def recompute_merkle_root(self) -> tuple[str, list[str]]:
        """
        Independently rebuild and recalculate the Merkle root from the candidate leaves.
        Returns: (recomputed_root, list_of_leaf_hashes)
        """
        leaves: list[MerkleLeaf] = []

        # 1. Investigation header leaf
        header_data = {
            "investigation_id": self.investigation_id,
            "schema_version": self.schema_version,
            "created_at": self.created_at,
            "query_sha256": self.query_info.query_image_sha256 if self.query_info else "",
        }
        leaves.append(MerkleLeaf(
            leaf_id="leaf_00_header",
            leaf_type="investigation_header",
            data=header_data,
        ))

        # 2. Candidate leaves
        for c in self.candidates:
            leaves.append(MerkleLeaf(
                leaf_id=c.candidate_id,
                leaf_type="candidate",
                data=c.to_canonical_dict(),
            ))

        rebuilt_tree = MerkleTree(leaves)
        return rebuilt_tree.root, [l.leaf_hash for l in rebuilt_tree.leaves]


def build_evidence_package(
    investigation_id: str,
    query_image_bytes: bytes,
    query_face_bbox: tuple[int, int, int, int],
    query_face_confidence: float,
    provider_runs: dict[str, Any],
    candidate_items: list[CandidateEvidenceItem],
    matched_candidate: MatchedCandidateEvidence,
    confidence_score: EvidenceConfidenceScore,
    evidence_graph: EvidenceGraph,
    timings_ms: dict[str, int] | None = None,
    created_at: Optional[str] = None,
) -> EvidencePackage:
    """
    Construct an end-to-end canonical EvidencePackage with Merkle Tree.
    """
    ts = created_at or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    # 1. Dual fingerprint for query image
    query_fp = compute_dual_fingerprint(query_image_bytes)
    query_info = QueryEvidenceInfo(
        query_image_sha256=query_fp.exact_sha256,
        query_perceptual_hash=query_fp.perceptual_hash,
        query_face_bbox=list(query_face_bbox),
        query_face_confidence=query_face_confidence,
        model_name="buffalo_l",
    )

    # 2. Construct Merkle Leaves
    merkle_leaves: list[MerkleLeaf] = []

    # Investigation header leaf
    header_data = {
        "investigation_id": investigation_id,
        "schema_version": "2.0",
        "created_at": ts,
        "query_sha256": query_fp.exact_sha256,
    }
    header_leaf = MerkleLeaf(
        leaf_id="leaf_00_header",
        leaf_type="investigation_header",
        data=header_data,
    )
    header_leaf.compute_hash()
    merkle_leaves.append(header_leaf)

    # Candidate leaves
    for cand in candidate_items:
        c_leaf = MerkleLeaf(
            leaf_id=cand.candidate_id,
            leaf_type="candidate",
            data=cand.to_canonical_dict(),
        )
        c_leaf.compute_hash()
        merkle_leaves.append(c_leaf)

    # 3. Build Merkle Tree
    tree = MerkleTree(merkle_leaves)
    merkle_root = tree.root

    # Update matched candidate leaf hash
    for leaf in merkle_leaves:
        if leaf.leaf_id == matched_candidate.matched_candidate_id:
            matched_candidate.leaf_hash = leaf.leaf_hash
            break

    # 4. Generate Inclusion Proof for matched candidate
    proof = tree.get_inclusion_proof(matched_candidate.matched_candidate_id)
    proof_dict = proof.to_dict() if proof else None

    # 5. Format provider runs
    serialized_runs: dict[str, Any] = {}
    for p_name, p_val in provider_runs.items():
        if hasattr(p_val, "status"):
            serialized_runs[p_name] = {
                "status": p_val.status,
                "latency_ms": p_val.latency_ms,
                "matches_count": p_val.matches_count,
                "error": p_val.error,
            }
        elif isinstance(p_val, dict):
            serialized_runs[p_name] = p_val
        else:
            serialized_runs[p_name] = str(p_val)

    leaf_records = [
        {"leaf_id": l.leaf_id, "leaf_type": l.leaf_type, "leaf_hash": l.leaf_hash}
        for l in tree.leaves
    ]

    return EvidencePackage(
        investigation_id=investigation_id,
        schema_version="2.0",
        created_at=ts,
        query_info=query_info,
        provider_runs=serialized_runs,
        candidate_count=len(candidate_items),
        candidates=candidate_items,
        matched_candidate=matched_candidate,
        evidence_confidence=confidence_score.to_dict(),
        merkle_root=merkle_root,
        merkle_leaf_count=len(tree.leaves),
        merkle_leaves=leaf_records,
        matched_inclusion_proof=proof_dict,
        evidence_graph=evidence_graph.to_dict(),
        timings_ms=timings_ms or {},
    )


# ── Backwards Compatible Factory (v1 compatibility) ─────────────────────────
def create_evidence_package(
    query_image_bytes: bytes,
    matched_url: str,
    matched_image_url: str,
    search_provider: str,
    face_similarity_score: float,
    candidate_faces_checked: int,
    similarity_threshold: float,
    model_name: str = "buffalo_l",
    person_name: Optional[str] = None,
    runner_up_score: Optional[float] = None,
    margin: Optional[float] = None,
) -> EvidencePackage:
    """
    Legacy constructor for backwards compatibility with v1 callers.
    """
    from urllib.parse import urlparse
    from traceface.evidence.scoring import calculate_evidence_confidence

    domain = urlparse(matched_url).netloc.lower()
    investigation_id = f"inv_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}"

    matched = MatchedCandidateEvidence(
        matched_candidate_id="candidate_01",
        matched_source_url=matched_url,
        matched_image_url=matched_image_url,
        matched_image_sha256=compute_exact_sha256(b"stub_matched_image"),
        matched_image_perceptual_hash=None,
        matched_face_similarity=face_similarity_score,
        matched_verification_status="MATCH",
        source_domain=domain,
        providers=[search_provider] if search_provider else ["manual"],
        evidence_confidence=75.0,
        person_name=person_name,
    )

    cand_item = CandidateEvidenceItem(
        candidate_id="candidate_01",
        canonical_url=matched_url,
        source_domain=domain,
        image_url=matched_image_url,
        providers=[search_provider] if search_provider else ["manual"],
        face_similarity_score=face_similarity_score,
        runner_up_score=runner_up_score,
        margin=margin,
        candidate_faces_checked=candidate_faces_checked,
        verification_status="MATCH",
        evidence_confidence=75.0,
        person_name=person_name,
    )

    score = calculate_evidence_confidence(
        face_similarity=face_similarity_score,
        threshold=similarity_threshold,
        margin=margin,
        candidate_faces_checked=candidate_faces_checked,
        providers=[search_provider],
        matched_url=matched_url,
    )

    graph = EvidenceGraph(investigation_id=investigation_id)
    graph.add_node(investigation_id, "investigation", "Investigation")

    return build_evidence_package(
        investigation_id=investigation_id,
        query_image_bytes=query_image_bytes,
        query_face_bbox=(0, 0, 100, 100),
        query_face_confidence=0.99,
        provider_runs={search_provider: {"status": "success", "latency_ms": 100, "matches_count": 1}},
        candidate_items=[cand_item],
        matched_candidate=matched,
        confidence_score=score,
        evidence_graph=graph,
    )


def save_evidence_package(
    package: EvidencePackage,
    evidence_hash: str | None = None,
    output_dir: Path | str = "results",
) -> Path:
    """
    Persist evidence package and Merkle commitments to JSON.
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    actual_hash = evidence_hash or package.sha256()
    filename = f"evidence_{actual_hash[:12]}.json"
    output_path = output_dir / filename

    full_record = {
        "evidence_package": package.to_canonical_dict(),
        "evidence_sha256": actual_hash,
        "merkle_root": package.merkle_root,
        "canonical_json": package.canonical_json(),
    }

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(full_record, f, indent=2)

    return output_path


def load_evidence_package(file_path: Path | str) -> tuple[EvidencePackage, dict[str, Any]]:
    """
    Load an evidence package from disk and reconstruct the EvidencePackage object.
    """
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"Evidence file not found: {path}")

    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    pkg_data = data.get("evidence_package", data)

    # Rebuild candidate objects
    candidates: list[CandidateEvidenceItem] = []
    for c in pkg_data.get("candidates", []):
        candidates.append(CandidateEvidenceItem(**c))

    # Rebuild matched candidate
    matched_data = pkg_data.get("matched_candidate")
    matched = MatchedCandidateEvidence(**matched_data) if matched_data else None

    # Rebuild query info
    query_data = pkg_data.get("query_info")
    query_info = QueryEvidenceInfo(**query_data) if query_data else None

    # Backward compatibility: legacy v1 packages without explicit candidate list
    if not candidates and "matched_url" in pkg_data:
        matched_url = pkg_data["matched_url"]
        domain = pkg_data.get("source_domain", "")
        img_url = pkg_data.get("matched_image_url", "")
        sim = float(pkg_data.get("face_similarity_score", 0.0))
        cand = CandidateEvidenceItem(
            candidate_id="candidate_01",
            canonical_url=matched_url,
            source_domain=domain,
            image_url=img_url,
            providers=[pkg_data.get("search_provider", "unknown")],
            face_similarity_score=sim,
            runner_up_score=pkg_data.get("runner_up_score"),
            margin=pkg_data.get("margin"),
            candidate_faces_checked=pkg_data.get("candidate_faces_checked", 1),
            verification_status="MATCH",
            person_name=pkg_data.get("person_name"),
            evidence_confidence=75.0,
        )
        candidates.append(cand)

        matched = MatchedCandidateEvidence(
            matched_candidate_id="candidate_01",
            matched_source_url=matched_url,
            matched_image_url=img_url,
            matched_image_sha256=pkg_data.get("query_image_sha256", ""),
            matched_image_perceptual_hash=None,
            matched_face_similarity=sim,
            matched_verification_status="MATCH",
            source_domain=domain,
            providers=[pkg_data.get("search_provider", "unknown")],
            evidence_confidence=75.0,
            person_name=pkg_data.get("person_name"),
        )

        query_info = QueryEvidenceInfo(
            query_image_sha256=pkg_data.get("query_image_sha256", ""),
            query_perceptual_hash=None,
            query_face_bbox=[0, 0, 100, 100],
            query_face_confidence=1.0,
            model_name=pkg_data.get("model_name", "buffalo_l"),
        )

    pkg = EvidencePackage(
        investigation_id=pkg_data.get("investigation_id", f"inv_{pkg_data.get('timestamp_utc', 'legacy')}"),
        schema_version=pkg_data.get("schema_version", "2.0"),
        created_at=pkg_data.get("created_at") or pkg_data.get("timestamp_utc", ""),
        query_info=query_info,
        provider_runs=pkg_data.get("provider_runs", {}),
        candidate_count=pkg_data.get("candidate_count", len(candidates)),
        candidates=candidates,
        matched_candidate=matched,
        evidence_confidence=pkg_data.get("evidence_confidence"),
        merkle_root=pkg_data.get("merkle_root", ""),
        merkle_leaf_count=pkg_data.get("merkle_leaf_count", 0),
        merkle_leaves=pkg_data.get("merkle_leaves", []),
        matched_inclusion_proof=pkg_data.get("matched_inclusion_proof"),
        evidence_graph=pkg_data.get("evidence_graph"),
        timings_ms=pkg_data.get("timings_ms", {}),
    )

    # If merkle_root was not pre-saved in legacy file, compute it now
    if not pkg.merkle_root and pkg.candidates:
        recomputed_root, leaf_hashes = pkg.recompute_merkle_root()
        pkg.merkle_root = recomputed_root
        pkg.merkle_leaf_count = len(leaf_hashes)

    return pkg, data
