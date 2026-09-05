"""
TraceFace — Deterministic Evidence Graph
=========================================
Represents verifiable, explainable relationships between investigation artifacts:
- Nodes: investigation, query_image, face, search, provider, candidate,
         source_page, verification, evidence_package
- Edges: searched_with, executed_by, discovered, originates_from,
         verified_against, produced, committed_in

Deterministic serialization enables full graph hashing into the evidence ledger.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class EvidenceNode:
    """A node in the evidence provenance graph."""
    id: str
    type: str                         # e.g., "query_image", "candidate", "provider"
    label: str
    properties: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "type": self.type,
            "label": self.label,
            "properties": self.properties,
        }


@dataclass
class EvidenceEdge:
    """A directed edge expressing a cryptographic or evidentiary relation."""
    source: str
    target: str
    relation: str                     # e.g., "discovered", "verified_against"
    properties: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "source": self.source,
            "target": self.target,
            "relation": self.relation,
            "properties": self.properties,
        }


class EvidenceGraph:
    """
    In-memory, deterministic JSON-serializable evidence graph.
    """

    def __init__(self, investigation_id: str) -> None:
        self.investigation_id = investigation_id
        self.nodes: dict[str, EvidenceNode] = {}
        self.edges: list[EvidenceEdge] = []

    def add_node(self, node_id: str, node_type: str, label: str, **properties: Any) -> EvidenceNode:
        node = EvidenceNode(id=node_id, type=node_type, label=label, properties=properties)
        self.nodes[node_id] = node
        return node

    def add_edge(self, source: str, target: str, relation: str, **properties: Any) -> EvidenceEdge:
        edge = EvidenceEdge(source=source, target=target, relation=relation, properties=properties)
        self.edges.append(edge)
        return edge

    def to_dict(self) -> dict:
        """
        Deterministic representation: sorted nodes by ID, sorted edges.
        """
        sorted_nodes = [self.nodes[k].to_dict() for k in sorted(self.nodes.keys())]
        sorted_edges = sorted(
            [e.to_dict() for e in self.edges],
            key=lambda e: (e["source"], e["target"], e["relation"])
        )
        return {
            "investigation_id": self.investigation_id,
            "node_count": len(sorted_nodes),
            "edge_count": len(sorted_edges),
            "nodes": sorted_nodes,
            "edges": sorted_edges,
        }

    def canonical_json(self) -> str:
        return json.dumps(self.to_dict(), sort_keys=True, separators=(",", ":"))


def build_investigation_graph(
    investigation_id: str,
    query_image_sha: str,
    query_face_bbox: tuple[int, int, int, int],
    query_face_conf: float,
    providers_run: dict[str, Any],
    candidates_data: list[dict[str, Any]],
    matched_candidate_id: str,
    verification_data: dict[str, Any],
    evidence_package_id: str,
) -> EvidenceGraph:
    """
    Construct complete investigation evidence graph.
    """
    graph = EvidenceGraph(investigation_id=investigation_id)

    # 1. Investigation root node
    graph.add_node(
        investigation_id,
        "investigation",
        f"Investigation {investigation_id}",
        schema_version="2.0",
    )

    # 2. Query Image node
    query_node_id = f"query_{query_image_sha[:12]}"
    graph.add_node(
        query_node_id,
        "query_image",
        "Input Face Image",
        sha256=query_image_sha,
    )
    graph.add_edge(investigation_id, query_node_id, "investigated_with")

    # 3. Query Face node
    face_node_id = f"face_query_primary"
    graph.add_node(
        face_node_id,
        "face",
        "Extracted Subject Face",
        bbox=list(query_face_bbox),
        confidence=round(query_face_conf, 4),
        model="buffalo_l_arcface",
    )
    graph.add_edge(query_node_id, face_node_id, "contains_face")

    # 4. Search Run node
    search_node_id = f"search_run_{investigation_id[:8]}"
    graph.add_node(
        search_node_id,
        "search",
        "Parallel Multi-Provider Search",
        provider_count=len(providers_run),
    )
    graph.add_edge(face_node_id, search_node_id, "searched_with")

    # 5. Provider nodes
    for prov_name, p_info in providers_run.items():
        prov_node_id = f"provider_{prov_name}"
        status = getattr(p_info, "status", str(p_info.get("status") if isinstance(p_info, dict) else "unknown"))
        latency = getattr(p_info, "latency_ms", int(p_info.get("latency_ms", 0) if isinstance(p_info, dict) else 0))
        graph.add_node(
            prov_node_id,
            "provider",
            f"Search Engine: {prov_name}",
            status=status,
            latency_ms=latency,
        )
        graph.add_edge(search_node_id, prov_node_id, "executed_by")

    # 6. Candidate nodes & edges
    for cand in candidates_data:
        c_id = cand["candidate_id"]
        graph.add_node(
            c_id,
            "candidate",
            f"Candidate {c_id}",
            canonical_url=cand.get("canonical_url", ""),
            source_domain=cand.get("source_domain", ""),
            providers=cand.get("providers", []),
        )
        graph.add_edge(search_node_id, c_id, "discovered")

        # Link each discovering provider to the candidate
        for prov in cand.get("providers", []):
            prov_node_id = f"provider_{prov}"
            if prov_node_id in graph.nodes:
                graph.add_edge(prov_node_id, c_id, "contributed")

        # Source page node
        page_node_id = f"page_{c_id}"
        graph.add_node(
            page_node_id,
            "source_page",
            cand.get("source_domain", "Web Page"),
            url=cand.get("canonical_url", ""),
        )
        graph.add_edge(c_id, page_node_id, "originates_from")

    # 7. Verification node for matched candidate
    if matched_candidate_id and matched_candidate_id in graph.nodes:
        verif_node_id = f"verification_{matched_candidate_id}"
        graph.add_node(
            verif_node_id,
            "verification",
            "ArcFace Cosine Verification",
            best_score=verification_data.get("best_score", 0.0),
            threshold=verification_data.get("threshold", 0.35),
            margin=verification_data.get("margin"),
            passed=verification_data.get("passed", False),
        )
        graph.add_edge(matched_candidate_id, verif_node_id, "subject_of")
        graph.add_edge(verif_node_id, face_node_id, "verified_against")

    # 8. Evidence Package commitment node
    pkg_node_id = f"package_{evidence_package_id[:12]}"
    graph.add_node(
        pkg_node_id,
        "evidence_package",
        "Cryptographic Evidence Package",
        package_id=evidence_package_id,
    )
    graph.add_edge(investigation_id, pkg_node_id, "committed_in")

    return graph
