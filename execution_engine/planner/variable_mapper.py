from typing import Any, Dict, Optional

from ..models.workflow import Step

TIP_TYPE_ALIASES = ["tip_type", "DiTi_type", "diti_type"]


def _resolve_tip_type(params: Dict[str, Any]) -> Optional[str]:
    """Return tip type from any accepted alias, normalized to 'tip_type'."""
    for alias in TIP_TYPE_ALIASES:
        if alias in params:
            return params[alias]
    return None


def _resolve_well_offsets(params: Dict[str, Any]) -> Any:
    """Normalize well_offset / well_offsets to a single key."""
    return params.get("well_offsets") or params.get("well_offset")


def _set_if(target: Dict[str, Any], key: str, value: Any) -> None:
    """Only write to target if value is not None.
    Runtime is strict — None values must never be passed through.
    """
    if value is not None:
        target[key] = value


class VariableMapper:
    """Maps Step params to a runtime variable dict for a specific method.

    Step-type-aware: each step family has its own mapping logic.
    Normalizes parameter aliases (e.g. DiTi_type -> tip_type).
    Only returns non-None values — the runtime adapter enforces strictness.
    """

    def map(self, step: Step, method_name: str) -> Dict[str, Any]:
        """Return runtime variables for the given step and method."""
        params = step.params
        step_type = step.type

        if step_type in ("reagent_distribution", "sample_transfer"):
            return self._map_distribution(params)

        if step_type in ("aspirate_volume", "dispense_volume", "mix_volume"):
            return self._map_liquid_operation(params, step_type)

        # "mix" is an extended alias for mix_volume used in some TDFs.
        # It accepts volume_uL and target in addition to the standard fields.
        if step_type == "mix":
            return self._map_mix(params)

        if step_type == "transfer_labware":
            return self._map_transfer_labware(params)

        if step_type == "get_tips":
            return self._map_get_tips(params)

        if step_type == "drop_tips_to_location":
            return self._map_drop_tips(params)

        if step_type == "empty_tips":
            return self._map_empty_tips(params)

        if step_type == "incubate":
            return self._map_incubate(params)

        # Fallback: pass through all non-None params as-is
        return {k: v for k, v in params.items() if v is not None}

    def _map_distribution(self, params: Dict[str, Any]) -> Dict[str, Any]:
        result: Dict[str, Any] = {}
        # Accept both volumes and volume_uL
        _set_if(result, "volumes", params.get("volumes") or params.get("volume_uL"))
        _set_if(result, "tip_type", _resolve_tip_type(params))
        _set_if(result, "liquid_class", params.get("liquid_class"))
        # Accept both labware_source/target and source/target shorthand
        _set_if(result, "labware_source", params.get("labware_source") or params.get("source"))
        _set_if(result, "labware_target", params.get("labware_target") or params.get("target"))
        _set_if(result, "selected_wells_source", params.get("selected_wells_source"))
        _set_if(result, "selected_wells_target", params.get("selected_wells_target"))
        _set_if(result, "number_replicates", params.get("number_replicates"))
        _set_if(result, "sample_direction", params.get("sample_direction"))
        _set_if(result, "replicate_direction", params.get("replicate_direction"))
        _set_if(result, "tips_per_well_source", params.get("tips_per_well_source"))
        _set_if(result, "sample_count", params.get("sample_count"))
        _set_if(result, "labware_empty_tips", params.get("labware_empty_tips"))
        return result

    def _map_liquid_operation(self, params: Dict[str, Any], step_type: str) -> Dict[str, Any]:
        result: Dict[str, Any] = {}
        _set_if(result, "volumes", params.get("volumes") or params.get("volume_uL"))
        _set_if(result, "labware", params.get("labware"))
        _set_if(result, "liquid_class", params.get("liquid_class"))
        _set_if(result, "well_offsets", _resolve_well_offsets(params))
        _set_if(result, "tip_indices", params.get("tip_indices"))
        if step_type == "mix_volume":
            _set_if(result, "cycles", params.get("cycles"))
        return result

    def _map_mix(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Handle the 'mix' step type (alias for mix_volume with extended field names)."""
        result: Dict[str, Any] = {}
        _set_if(result, "volumes", params.get("volumes") or params.get("volume_uL"))
        # Accept both labware and target as the labware identifier
        _set_if(result, "labware", params.get("labware") or params.get("target"))
        _set_if(result, "liquid_class", params.get("liquid_class"))
        _set_if(result, "tip_type", _resolve_tip_type(params))
        _set_if(result, "cycles", params.get("cycles"))
        _set_if(result, "well_offsets", _resolve_well_offsets(params))
        _set_if(result, "tip_indices", params.get("tip_indices"))
        return result

    def _map_transfer_labware(self, params: Dict[str, Any]) -> Dict[str, Any]:
        result: Dict[str, Any] = {}
        _set_if(result, "labware_name", params.get("labware_name"))
        _set_if(result, "target_location", params.get("target_location"))
        _set_if(result, "target_position", params.get("target_position"))
        return result

    def _map_get_tips(self, params: Dict[str, Any]) -> Dict[str, Any]:
        result: Dict[str, Any] = {}
        _set_if(result, "tip_type", _resolve_tip_type(params))
        _set_if(result, "tip_indices", params.get("tip_indices"))
        _set_if(result, "airgap_volume", params.get("airgap_volume"))
        _set_if(result, "airgap_speed", params.get("airgap_speed"))
        return result

    def _map_drop_tips(self, params: Dict[str, Any]) -> Dict[str, Any]:
        result: Dict[str, Any] = {}
        _set_if(result, "labware", params.get("labware"))
        _set_if(result, "tip_indices", params.get("tip_indices"))
        return result

    def _map_empty_tips(self, params: Dict[str, Any]) -> Dict[str, Any]:
        result: Dict[str, Any] = {}
        _set_if(result, "labware_empty_tips", params.get("labware_empty_tips"))
        # Some TDFs use labware / liquid_class / well_offsets on empty_tips
        _set_if(result, "labware", params.get("labware"))
        _set_if(result, "liquid_class", params.get("liquid_class"))
        _set_if(result, "well_offsets", _resolve_well_offsets(params))
        _set_if(result, "tip_indices", params.get("tip_indices"))
        return result

    def _map_incubate(self, params: Dict[str, Any]) -> Dict[str, Any]:
        result: Dict[str, Any] = {}
        # Accept both duration_seconds and time_s
        _set_if(result, "duration_seconds", params.get("duration_seconds") or params.get("time_s"))
        _set_if(result, "temperature_celsius", params.get("temperature_celsius"))
        # Accept both device and location
        _set_if(result, "device", params.get("device") or params.get("location"))
        _set_if(result, "labware", params.get("labware"))
        return result
