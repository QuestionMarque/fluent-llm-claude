from ..models.state import State
from ..models.workflow import Step


class StateManager:
    """Tracks and mutates execution state after each step completes.

    Extension hook: add new state fields to the State dataclass and handle
    them in update() without breaking existing behavior.
    """

    def __init__(self):
        self.state = State()

    def update(self, step: Step, success: bool) -> None:
        """Apply state changes that result from executing a step."""
        if not success:
            return  # Don't mutate state on failed steps

        step_type = step.type
        params = step.params

        if step_type == "get_tips":
            self.state.load_tip()

        elif step_type in ("drop_tips_to_location", "empty_tips"):
            self.state.unload_tip()

        elif step_type in ("reagent_distribution", "sample_transfer", "dispense_volume"):
            volumes = params.get("volumes") or params.get("volume_uL", 0)
            volume = sum(volumes) if isinstance(volumes, list) else float(volumes or 0)
            labware_key = params.get("labware_target") or params.get("target") or "unknown"
            self.state.add_volume(labware_key, volume)

        elif step_type == "aspirate_volume":
            volumes = params.get("volumes") or params.get("volume_uL", 0)
            volume = sum(volumes) if isinstance(volumes, list) else float(volumes or 0)
            labware_key = params.get("labware") or "unknown"
            self.state.remove_volume(labware_key, volume)

        self.state.execution_history.append({
            "step_type": step_type,
            "step_id": step.id,
            "success": success,
        })

    def get_state(self) -> State:
        return self.state
