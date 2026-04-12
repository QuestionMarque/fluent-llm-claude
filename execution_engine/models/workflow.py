from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

# STEP_SCHEMA is the single source of truth for step structure.
# validation/validator_wrapper.py reads required fields from here.
# Do NOT duplicate required-field logic anywhere else.
STEP_SCHEMA: Dict[str, Dict[str, List[str]]] = {
    "reagent_distribution": {
        "required": ["volumes", "labware_source", "labware_target"],
        "optional": [
            "tip_type", "DiTi_type", "diti_type",
            "liquid_class",
            "selected_wells_source", "selected_wells_target",
            "number_replicates", "sample_direction", "replicate_direction",
            "tips_per_well_source",
        ],
    },
    "sample_transfer": {
        "required": ["volumes", "labware_source", "labware_target"],
        "optional": [
            "tip_type", "DiTi_type", "diti_type",
            "liquid_class",
            "selected_wells_source", "selected_wells_target",
            "number_replicates", "sample_direction", "replicate_direction",
            "tips_per_well_source",
        ],
    },
    "aspirate_volume": {
        "required": ["volumes", "labware"],
        "optional": [
            "liquid_class",
            "well_offset", "well_offsets",
        ],
    },
    "dispense_volume": {
        "required": ["volumes", "labware"],
        "optional": [
            "liquid_class",
            "well_offset", "well_offsets",
        ],
    },
    "mix_volume": {
        "required": ["volumes", "labware"],
        "optional": [
            "liquid_class",
            "well_offset", "well_offsets",
            "cycles",
            "tip_indices",
        ],
    },
    # "mix" is an alias-style step used in some TDFs. Uses volume_uL / target
    # instead of volumes / labware. Maps to MixVolume method in the registry.
    "mix": {
        "required": [],
        "optional": [
            "volumes", "volume_uL",
            "cycles",
            "labware", "target",
            "liquid_class",
            "tip_type", "DiTi_type", "diti_type",
            "well_offsets", "well_offset",
            "tip_indices",
        ],
    },
    "incubate": {
        "required": ["duration_seconds"],
        "optional": [
            "temperature_celsius", "device",
            # Extended aliases used in some TDFs
            "time_s", "location", "labware",
        ],
    },
    "transfer_labware": {
        "required": ["labware_name", "target_location"],
        "optional": ["target_position"],
    },
    "get_tips": {
        "required": ["tip_type"],
        "optional": [
            "DiTi_type", "diti_type",
            "tip_indices", "airgap_volume", "airgap_speed",
        ],
    },
    "drop_tips_to_location": {
        "required": ["labware"],
        "optional": ["tip_indices"],
    },
    "empty_tips": {
        "required": [],
        "optional": [
            "labware_empty_tips", "labware",
            "liquid_class", "well_offsets", "well_offset",
            "tip_indices",
        ],
    },
}


@dataclass
class Step:
    """A single executable step in a workflow.

    type must match a key in STEP_SCHEMA.
    params holds all step-specific arguments.
    id is optional — used for logging and traceability.
    """
    type: str
    params: Dict[str, Any] = field(default_factory=dict)
    id: Optional[str] = None


@dataclass
class Workflow:
    """An ordered sequence of Steps ready for validation and planning.

    Currently linear. Extension hooks for branching/loops live in
    workflow/dependency_resolver.py — add them there without touching
    the core linear path.
    """
    steps: List[Step] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
