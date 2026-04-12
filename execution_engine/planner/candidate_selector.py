from typing import List, Optional

from ..capability_registry.registry import CapabilityRegistry
from ..capability_registry.models import Method
from ..models.workflow import Step

TIP_TYPE_ALIASES = ["tip_type", "DiTi_type", "diti_type"]


def _get_tip_type(params: dict) -> Optional[str]:
    for alias in TIP_TYPE_ALIASES:
        if alias in params:
            return params[alias]
    return None


class CandidateSelector:
    """Hard filter: removes methods that cannot execute this step at all.

    No scoring here — only binary pass/fail checks:
    - method must support the step type
    - if tip_type is specified, it must appear in method.tip_types
    - if volumes are specified, max volume must fit within method range
    - if both tip and liquid class are specified, they must be compatible
    """

    def __init__(self, registry: CapabilityRegistry, enable_liquid_inference: bool = False):
        self.registry = registry
        self.enable_liquid_inference = enable_liquid_inference

    def select(self, step: Step) -> List[Method]:
        """Return methods that pass all hard constraints for this step."""
        candidates = self.registry.methods_supporting(step.type)
        return [m for m in candidates if self._passes(step, m)]

    def _passes(self, step: Step, method: Method) -> bool:
        params = step.params
        tip_name = _get_tip_type(params)
        liquid_name = params.get("liquid_class")
        volumes = params.get("volumes") or params.get("volume_uL")

        # Tip hard filter: if specified, must exist in method's tip list
        if tip_name and method.tip_types:
            if tip_name not in method.tip_types:
                return False

        # Volume hard filter: max volume must fit in method range
        if volumes is not None:
            max_vol = max(volumes) if isinstance(volumes, list) else float(volumes)
            if max_vol < method.min_volume_uL or max_vol > method.max_volume_uL:
                return False

        # Liquid/tip compatibility hard filter
        if tip_name and liquid_name:
            if not self.registry.tip_compatible_with_liquid(tip_name, liquid_name):
                return False

        return True
