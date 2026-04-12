from dataclasses import dataclass, field
from typing import Dict, List, Optional

from .models import Device, TipType, LiquidClass, Labware, Method, Rule


@dataclass
class CapabilityRegistry:
    """Central capability registry for the execution engine.

    All planning and validation decisions must be grounded here.
    No hardcoded method/tip/liquid knowledge anywhere else in the system.

    Note on iteration: registry.methods is a dict — use .values() when iterating.
    Typed objects (Method, TipType, etc.) must not be treated as plain dicts.
    """
    devices: Dict[str, Device] = field(default_factory=dict)
    tips: Dict[str, TipType] = field(default_factory=dict)
    liquid_classes: Dict[str, LiquidClass] = field(default_factory=dict)
    labware: Dict[str, Labware] = field(default_factory=dict)
    methods: Dict[str, Method] = field(default_factory=dict)
    rules: List[Rule] = field(default_factory=list)
    # tip_name -> list of compatible liquid class names
    tip_liquid_compatibility: Dict[str, List[str]] = field(default_factory=dict)

    # --- Query helpers ---

    def get_device(self, name: str) -> Optional[Device]:
        return self.devices.get(name)

    def get_tip(self, name: str) -> Optional[TipType]:
        return self.tips.get(name)

    def get_liquid_class(self, name: str) -> Optional[LiquidClass]:
        return self.liquid_classes.get(name)

    def get_labware(self, name: str) -> Optional[Labware]:
        return self.labware.get(name)

    def get_method(self, name: str) -> Optional[Method]:
        return self.methods.get(name)

    def methods_supporting(self, step_type: str) -> List[Method]:
        """Return all methods whose supports list includes step_type."""
        return [m for m in self.methods.values() if step_type in m.supports]

    def tip_compatible_with_liquid(self, tip_name: str, liquid_name: str) -> bool:
        """Check the compatibility matrix.

        Returns True if compatible, or True if the tip has no entry
        (unknown = assume compatible to avoid false positives).
        """
        compatible = self.tip_liquid_compatibility.get(tip_name)
        if compatible is None:
            return True
        return liquid_name in compatible

    def infer_liquid_class_for_tip(self, tip_name: str) -> Optional[str]:
        """Return the first compatible liquid class for a tip, if any."""
        compatible = self.tip_liquid_compatibility.get(tip_name, [])
        return compatible[0] if compatible else None
