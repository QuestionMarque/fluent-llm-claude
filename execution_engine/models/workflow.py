from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

# STEP_SCHEMA is the single source of truth for step structure.
# validation/validator_wrapper.py reads required fields from here.
# Do NOT duplicate required-field logic anywhere else.
STEP_SCHEMA: Dict[str, Dict[str, List[str]]] = {
    "reagent_distribution": {
        "required": [
            "labware_empty_tips",
            "volumes",
            "sample_count",
            "DiTi_type",
            "DiTi_waste",
            "labware_source",
            "labware_target",
            "liquid_class",
            "selected_wells_source",
            "selected_wells_target"
        ],
        "optional": [
            "DynamicDiTiHandling",
            "DynamicDiTiHandling_rule",
            "LiquidClass_EmptyTip",
            "max_tip_reuse",
            "multi_dispense",
            "sample_direction",
            "number_replicates",
            "replicate_direction",
            "airgap_volume",
            "airgap_speed",
            "tips_per_well_source",
            "well_offset_source",
            "tips_per_well_target",
            "well_offset_target",
            "tip_indices",
        ],
    },
    "sample_transfer": {
        "required": [
            "labware_empty_tips",
            "volumes",
            "sample_count",
            "DiTi_type",
            "DiTi_waste",
            "labware_source",
            "labware_target",
            "selected_wells_source",
            "selected_wells_target",
            "liquid_class",
        ],
        "optional": [
            "DynamicDiTiHandling",
            "DynamicDiTiHandling_rule",
            "pooling",
            "samples_per_pool",
            "LiquidClass_EmptyTip",
            "max_tip_reuse",
            "multi_dispense",
            "sample_direction",
            "number_replicates",
            "replicate_direction",
            "airgap_volume",
            "airgap_speed",
            "tips_per_well_source",
            "well_offset_source",
            "tips_per_well_target",
            "well_offset_target",
            "tip_indices",
        ],
    },
    "aspirate_volume": {
        "required": [
            "volumes",
            "labware",
            "liquid_class",
        ],
        "optional": [
            "well_offsets",
            "tip_indices",
        ],
    },
    "dispense_volume": {
        "required": [
            "volumes",
            "labware",
            "liquid_class",
        ],
        "optional": [
            "well_offsets",
            "tip_indices",
        ],
    },
    "mix_volume": {
        "required": [
            "volumes",
            "labware",
            "liquid_class",
        ],
        "optional": [
            "well_offsets",
            "tip_indices",
            "cycles",
        ],
    },
    # "mix" is an alias-style step used in some IRs. Uses volume_uL / target
    # instead of volumes / labware. Maps to MixVolume method in the registry.
    # not a valid FC step
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
    # not a valid FC step — used in some IRs as an alias for incubate with temp/time
    "incubate": {
        "required": ["duration_seconds"],
        "optional": [
            "temperature_celsius", "device",
            # Extended aliases used in some IRs
            "time_s", "location", "labware",
        ],
    },
    "transfer_labware": {
        "required": [
            "labware_name",
            "target_location",
        ],
        "optional": [
            "target_position",
            "only_use_selected_site",
        ],
    },
    "get_tips": {
        "required": [
            "diti_type",
        ],
        "optional": [
            "airgap_volume",
            "airgap_speed",
            "tip_indices",
        ],
    },
    "drop_tips_to_location": {
        "required": [
            "labware",
        ],
        "optional": [
            "tip_indices",
        ],
    },
    "empty_tips": {
        "required": [
            "labware",
        ],
        "optional": [
            "liquid_class",
            "tip_indices",
            "well_offsets",
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
