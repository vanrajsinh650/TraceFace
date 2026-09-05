"""
TraceFace — Multi-Signal Evidence Confidence Scoring
=====================================================
Calculates a transparent, multi-signal evidence confidence score (0-100).

Signals:
1. Face ArcFace Cosine Similarity (max 45 pts)
2. Face Score Runner-Up Margin (max 20 pts)
3. Multi-Provider Agreement (max 15 pts)
4. Source Domain Authenticity (max 10 pts)
5. Candidate Image Resolution / Fidelity (max 10 pts)

DISCLAIMER:
This score represents cryptographic and biometric evidence strength.
It does NOT constitute proof of real-world identity or legal certainty.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional
from urllib.parse import urlparse

# Preferred social and profile platforms
_HIGH_CONFIDENCE_DOMAINS = {
    "instagram.com", "x.com", "twitter.com", "facebook.com",
    "linkedin.com", "reddit.com", "tiktok.com", "vk.com",
}


@dataclass
class ScoreComponent:
    """Breakdown of an individual evidence score signal."""
    name: str
    points: float
    max_points: float
    raw_value: str
    assessment: str


@dataclass
class EvidenceConfidenceScore:
    """Composite explainable evidence confidence assessment."""
    total_score: float             # 0.0 – 100.0
    rating: str                    # "VERY_STRONG", "STRONG", "MODERATE", "LOW"
    components: list[ScoreComponent] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "total_score": round(self.total_score, 2),
            "rating": self.rating,
            "components": [
                {
                    "name": c.name,
                    "points": round(c.points, 2),
                    "max_points": round(c.max_points, 2),
                    "raw_value": c.raw_value,
                    "assessment": c.assessment,
                }
                for c in self.components
            ]
        }


def calculate_evidence_confidence(
    face_similarity: float,
    threshold: float = 0.35,
    margin: Optional[float] = None,
    candidate_faces_checked: int = 1,
    providers: list[str] | None = None,
    matched_url: str = "",
    image_width: int = 0,
    image_height: int = 0,
) -> EvidenceConfidenceScore:
    """
    Compute explainable evidence confidence score out of 100.
    """
    components: list[ScoreComponent] = []

    # 1. Face similarity (max 45 pts)
    # Scaled from threshold (0.35) to high ceiling (0.75+)
    if face_similarity <= threshold:
        sim_pts = max(0.0, (face_similarity / max(0.01, threshold)) * 15.0)
        sim_assess = "Below threshold"
    else:
        norm_factor = min(1.0, (face_similarity - threshold) / max(0.01, (0.75 - threshold)))
        sim_pts = 20.0 + (norm_factor * 25.0)
        sim_assess = "High match" if face_similarity >= 0.70 else "Valid match"

    components.append(ScoreComponent(
        name="face_similarity",
        points=sim_pts,
        max_points=45.0,
        raw_value=f"{face_similarity:.4f} (threshold: {threshold:.2f})",
        assessment=sim_assess,
    ))

    # 2. Runner-up score margin (max 20 pts)
    if candidate_faces_checked <= 1 or margin is None:
        margin_pts = 18.0
        margin_assess = "Single isolated face in candidate image"
        margin_val = "isolated_face"
    else:
        norm_margin = min(1.0, max(0.0, margin / 0.40))
        margin_pts = norm_margin * 20.0
        margin_assess = f"Clear margin over {candidate_faces_checked - 1} other faces" if margin >= 0.20 else "Narrow margin"
        margin_val = f"+{margin:.4f}"

    components.append(ScoreComponent(
        name="runner_up_margin",
        points=margin_pts,
        max_points=20.0,
        raw_value=margin_val,
        assessment=margin_assess,
    ))

    # 3. Provider agreement (max 15 pts)
    prov_list = providers or []
    num_prov = len(set(p.lower() for p in prov_list if p))
    if num_prov >= 3:
        prov_pts = 15.0
        prov_assess = f"Corroborated across {num_prov} independent search engines"
    elif num_prov == 2:
        prov_pts = 11.0
        prov_assess = f"Corroborated across 2 search engines"
    elif num_prov == 1:
        prov_pts = 6.0
        prov_assess = f"Discovered by 1 engine ({prov_list[0]})"
    else:
        prov_pts = 3.0
        prov_assess = "Direct or fallback discovery"

    components.append(ScoreComponent(
        name="provider_agreement",
        points=prov_pts,
        max_points=15.0,
        raw_value=f"{num_prov} providers ({', '.join(prov_list) or 'unknown'})",
        assessment=prov_assess,
    ))

    # 4. Source domain quality (max 10 pts)
    netloc = urlparse(matched_url).netloc.lower()
    is_social = any(d in netloc for d in _HIGH_CONFIDENCE_DOMAINS)
    if is_social:
        source_pts = 10.0
        source_assess = f"Verified social/profile platform ({netloc})"
    elif netloc:
        source_pts = 6.5
        source_assess = f"Public web domain ({netloc})"
    else:
        source_pts = 3.0
        source_assess = "Direct link without domain metadata"

    components.append(ScoreComponent(
        name="source_quality",
        points=source_pts,
        max_points=10.0,
        raw_value=netloc or "unknown",
        assessment=source_assess,
    ))

    # 5. Image fidelity / face detectability (max 10 pts)
    min_dim = min(image_width, image_height) if image_width and image_height else 0
    if min_dim >= 400:
        fidelity_pts = 10.0
        fidelity_assess = f"High resolution ({image_width}x{image_height})"
    elif min_dim >= 150:
        fidelity_pts = 8.0
        fidelity_assess = f"Standard resolution ({image_width}x{image_height})"
    elif min_dim > 0:
        fidelity_pts = 5.0
        fidelity_assess = f"Low resolution thumbnail ({image_width}x{image_height})"
    else:
        fidelity_pts = 7.0
        fidelity_assess = "Standard candidate image"

    components.append(ScoreComponent(
        name="image_fidelity",
        points=fidelity_pts,
        max_points=10.0,
        raw_value=f"{image_width}x{image_height}" if image_width else "valid_bytes",
        assessment=fidelity_assess,
    ))

    total = sum(c.points for c in components)
    total = max(0.0, min(100.0, total))

    if total >= 80.0:
        rating = "VERY_STRONG"
    elif total >= 65.0:
        rating = "STRONG"
    elif total >= 45.0:
        rating = "MODERATE"
    else:
        rating = "LOW"

    return EvidenceConfidenceScore(
        total_score=total,
        rating=rating,
        components=components,
    )
