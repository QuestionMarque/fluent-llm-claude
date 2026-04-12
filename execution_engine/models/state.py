from dataclasses import dataclass, field
from typing import Any, Dict, List


@dataclass
class State:
    """Lightweight execution state mutated by StateManager after each step.

    tip_loaded:        whether a tip is currently mounted on the instrument.
    well_volumes:      maps well identifiers (e.g. "A1") to current volume µL.
    execution_history: list of step outcome dicts for audit trail.
    """
    tip_loaded: bool = False
    well_volumes: Dict[str, float] = field(default_factory=dict)
    execution_history: List[Dict[str, Any]] = field(default_factory=list)

    def load_tip(self) -> None:
        self.tip_loaded = True

    def unload_tip(self) -> None:
        self.tip_loaded = False

    def add_volume(self, well: str, volume_uL: float) -> None:
        self.well_volumes[well] = self.well_volumes.get(well, 0.0) + volume_uL

    def remove_volume(self, well: str, volume_uL: float) -> None:
        current = self.well_volumes.get(well, 0.0)
        self.well_volumes[well] = max(0.0, current - volume_uL)
