"""
TraceFace — Unit Tests for Evidence Graph
=========================================
Tests graph node creation, relationship edges, and deterministic canonical representation.
"""
import unittest
from traceface.evidence.graph import EvidenceGraph, build_investigation_graph


class TestEvidenceGraph(unittest.TestCase):

    def test_evidence_graph_nodes_and_edges(self):
        graph = EvidenceGraph("inv_123")
        graph.add_node("n1", "query_image", "Input Image", sha256="abc")
        graph.add_node("n2", "face", "Face Crop", bbox=[10, 10, 50, 50])
        graph.add_edge("n1", "n2", "contains_face")

        d = graph.to_dict()
        self.assertEqual(d["node_count"], 2)
        self.assertEqual(d["edge_count"], 1)
        self.assertEqual(len(d["nodes"]), 2)
        self.assertEqual(d["edges"][0]["relation"], "contains_face")

    def test_investigation_graph_builder(self):
        graph = build_investigation_graph(
            investigation_id="inv_test",
            query_image_sha="a" * 64,
            query_face_bbox=(10, 20, 100, 120),
            query_face_conf=0.98,
            providers_run={"yandex": {"status": "success", "latency_ms": 120, "matches_count": 5}},
            candidates_data=[
                {
                    "candidate_id": "candidate_01",
                    "canonical_url": "https://example.com/post",
                    "source_domain": "example.com",
                    "providers": ["yandex"],
                }
            ],
            matched_candidate_id="candidate_01",
            verification_data={"best_score": 0.75, "threshold": 0.35, "passed": True},
            evidence_package_id="inv_test",
        )

        node_types = {n["type"] for n in graph.to_dict()["nodes"]}
        expected_types = {
            "investigation", "query_image", "face", "search",
            "provider", "candidate", "source_page", "verification", "evidence_package"
        }
        self.assertTrue(expected_types.issubset(node_types))

        # Determinism: canonical_json must be strictly identical on repeated calls
        json1 = graph.canonical_json()
        json2 = graph.canonical_json()
        self.assertEqual(json1, json2)


if __name__ == "__main__":
    unittest.main()
