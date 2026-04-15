"""RuntimeCall — concrete method invocation produced from a validated Step.

The variable-mapping helpers below translate `step.params` into the runtime
variable dict expected by the corresponding FluentControl method. They handle
parameter aliases (`DiTi_type` → `tip_type`, `well_offset` → `well_offsets`),
filter out IR fields that are not runtime variables, and drop None values
so the strict runtime adapter never has to.

`RuntimeCall.from_step(step, registry)` is the only public entry point.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from ..capability_registry.registry import CapabilityRegistry
    from .workflow import Step


# ---------------------------------------------------------------------------
# Variable-mapping helpers (module-private)
# ---------------------------------------------------------------------------

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


def _map_variables(step: "Step") -> Dict[str, Any]:
    """Translate step.params into a runtime variable dict.

    Step-type-aware: each step family has its own field set. Unknown step
    types fall back to an identity pass-through (filtered for None).
    """
    params = step.params
    step_type = step.type

    if step_type in ("reagent_distribution", "sample_transfer"):
        return _map_distribution(params)

    if step_type in ("aspirate_volume", "dispense_volume", "mix_volume"):
        return _map_liquid_operation(params, step_type)

    if step_type == "transfer_labware":
        return _map_transfer_labware(params)

    if step_type == "get_tips":
        return _map_get_tips(params)

    if step_type == "drop_tips_to_location":
        return _map_drop_tips(params)

    if step_type == "empty_tips":
        return _map_empty_tips(params)

    # Fallback: pass through all non-None params as-is
    return {k: v for k, v in params.items() if v is not None}


def _map_distribution(params: Dict[str, Any]) -> Dict[str, Any]:
    result: Dict[str, Any] = {}
    _set_if(result, "volumes", params.get("volumes") or params.get("volume_uL"))
    _set_if(result, "tip_type", _resolve_tip_type(params))
    _set_if(result, "liquid_class", params.get("liquid_class"))
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


def _map_liquid_operation(params: Dict[str, Any], step_type: str) -> Dict[str, Any]:
    result: Dict[str, Any] = {}
    _set_if(result, "volumes", params.get("volumes") or params.get("volume_uL"))
    _set_if(result, "labware", params.get("labware"))
    _set_if(result, "liquid_class", params.get("liquid_class"))
    _set_if(result, "well_offsets", _resolve_well_offsets(params))
    _set_if(result, "tip_indices", params.get("tip_indices"))
    if step_type == "mix_volume":
        _set_if(result, "cycles", params.get("cycles"))
    return result


def _map_transfer_labware(params: Dict[str, Any]) -> Dict[str, Any]:
    result: Dict[str, Any] = {}
    _set_if(result, "labware_name", params.get("labware_name"))
    _set_if(result, "target_location", params.get("target_location"))
    _set_if(result, "target_position", params.get("target_position"))
    return result


def _map_get_tips(params: Dict[str, Any]) -> Dict[str, Any]:
    result: Dict[str, Any] = {}
    _set_if(result, "tip_type", _resolve_tip_type(params))
    _set_if(result, "tip_indices", params.get("tip_indices"))
    _set_if(result, "airgap_volume", params.get("airgap_volume"))
    _set_if(result, "airgap_speed", params.get("airgap_speed"))
    return result


def _map_drop_tips(params: Dict[str, Any]) -> Dict[str, Any]:
    result: Dict[str, Any] = {}
    _set_if(result, "labware", params.get("labware"))
    _set_if(result, "tip_indices", params.get("tip_indices"))
    return result


def _map_empty_tips(params: Dict[str, Any]) -> Dict[str, Any]:
    result: Dict[str, Any] = {}
    _set_if(result, "labware_empty_tips", params.get("labware_empty_tips"))
    _set_if(result, "labware", params.get("labware"))
    _set_if(result, "liquid_class", params.get("liquid_class"))
    _set_if(result, "well_offsets", _resolve_well_offsets(params))
    _set_if(result, "tip_indices", params.get("tip_indices"))
    return result


# ---------------------------------------------------------------------------
# RuntimeCall
# ---------------------------------------------------------------------------

@dataclass
class RuntimeCall:
    """A concrete method invocation ready for the runtime adapter.

    Built from a validated Step via `RuntimeCall.from_step(step, registry)`.
    The registry is consulted for the one method that supports the step
    type — the 1:1 invariant is guaranteed by RegistryValidator at load
    time, so no selection logic is needed.

    method_name: FluentControl method to invoke
    variables:   key-value pairs passed to SetVariableValue
    step_id:     mirrors the originating Step.id for traceability
    """
    method_name: str
    variables: Dict[str, Any] = field(default_factory=dict)
    step_id: Optional[str] = None

    @classmethod
    def from_step(cls, step: "Step", registry: "CapabilityRegistry") -> "RuntimeCall":
        """Build a RuntimeCall by looking up the supporting method and
        translating step.params into runtime variables.

        Raises ValueError if no method in the registry supports the step
        type. For library and LLM IRs this cannot happen — validation
        rejects unknown step types upstream and the registry loader
        refuses any registry that doesn't cover STEP_SCHEMA. The check
        remains as a defensive guard for direct callers that bypass
        validation.
        """
        methods = registry.methods_supporting(step.type)
        if not methods:
            raise ValueError(
                f"No method in the registry supports step type '{step.type}'. "
                "The step type is unknown — validation should have rejected it."
            )
        return cls(
            method_name=methods[0].name,
            variables=_map_variables(step),
            step_id=step.id,
        )
