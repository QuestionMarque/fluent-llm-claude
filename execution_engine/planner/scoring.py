from typing import Dict, List, Optional, Tuple

from ..capability_registry.registry import CapabilityRegistry
from ..capability_registry.models import Method
from ..models.workflow import Step

TIP_TYPE_ALIASES = ["tip_type", "DiTi_type", "diti_type"]

# Scoring weights — tune to reflect operational priorities.
# All weights must sum to 1.0.
WEIGHTS: Dict[str, float] = {
    "coverage": 0.25,    # method explicitly supports this step type
    "tip":      0.20,    # tip type present and matched
    "volume":   0.20,    # volume within method range (well-centered = higher)
    "liquid":   0.15,    # liquid class present and matched
    "efficiency": 0.10,  # prefers specialized methods over general ones
    "risk":     0.10,    # penalty for tip/liquid incompatibility
}


def _get_tip_type(params: dict) -> Optional[str]:
    for alias in TIP_TYPE_ALIASES:
        if alias in params:
            return params[alias]
    return None


class ScoringEngine:
    """Soft ranking: assigns a weighted score to each candidate method.

    Returns (score, reasoning) where score is in [0.0, 1.0].
    Higher score = better fit for this step.
    Reasoning is a human-readable trace of the scoring decision.
    """

    def __init__(self, registry: CapabilityRegistry):
        self.registry = registry

    def score(self, step: Step, method: Method) -> Tuple[float, str]:
        params = step.params
        tip_name = _get_tip_type(params)
        liquid_name = params.get("liquid_class")
        volumes = params.get("volumes") or params.get("volume_uL")

        scores: Dict[str, float] = {}
        reasons: List[str] = []

        # Coverage: method supports this step type (should always be true post-selection)
        scores["coverage"] = 1.0 if step.type in method.supports else 0.0
        reasons.append(f"coverage={'yes' if scores['coverage'] else 'no'}")

        # Tip dimension
        if not tip_name:
            scores["tip"] = 0.5  # neutral when unspecified
            reasons.append("tip=unspecified(neutral)")
        elif tip_name in method.tip_types:
            scores["tip"] = 1.0
            reasons.append(f"tip='{tip_name}' matched")
        else:
            scores["tip"] = 0.0
            reasons.append(f"tip='{tip_name}' not in method")

        # Volume dimension
        if volumes is None:
            scores["volume"] = 0.5  # neutral when unspecified
            reasons.append("volume=unspecified(neutral)")
        else:
            max_vol = max(volumes) if isinstance(volumes, list) else float(volumes)
            if method.min_volume_uL <= max_vol <= method.max_volume_uL:
                # Score slightly lower if volume is near the extremes of the range
                span = method.max_volume_uL - method.min_volume_uL
                if span > 0:
                    center = (method.min_volume_uL + method.max_volume_uL) / 2
                    dist_from_center = abs(max_vol - center) / (span / 2)
                    scores["volume"] = max(0.5, 1.0 - dist_from_center * 0.3)
                else:
                    scores["volume"] = 1.0
                reasons.append(
                    f"volume={max_vol}µL in [{method.min_volume_uL}, {method.max_volume_uL}]"
                )
            else:
                scores["volume"] = 0.0
                reasons.append(f"volume={max_vol}µL out of range")

        # Liquid class dimension
        if not liquid_name:
            scores["liquid"] = 0.5  # neutral when unspecified
            reasons.append("liquid=unspecified(neutral)")
        elif liquid_name in method.liquid_classes:
            scores["liquid"] = 1.0
            reasons.append(f"liquid='{liquid_name}' matched")
        else:
            scores["liquid"] = 0.0
            reasons.append(f"liquid='{liquid_name}' not in method")

        # Efficiency: prefer more specialized methods (fewer step types supported)
        specificity = 1.0 / max(len(method.supports), 1)
        scores["efficiency"] = min(1.0, specificity * 2)
        reasons.append(f"efficiency=specificity({len(method.supports)} step type(s))")

        # Risk: penalize tip/liquid incompatibility
        risk_penalty = 0.0
        if tip_name and liquid_name:
            if not self.registry.tip_compatible_with_liquid(tip_name, liquid_name):
                risk_penalty = 1.0
                reasons.append("risk=tip/liquid incompatible(penalty)")
        scores["risk"] = 1.0 - risk_penalty

        # Weighted sum
        total = sum(WEIGHTS[dim] * scores[dim] for dim in WEIGHTS)
        reasoning = "; ".join(reasons)
        return round(total, 4), reasoning
