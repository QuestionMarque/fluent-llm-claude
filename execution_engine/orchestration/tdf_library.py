"""Pre-defined TDF (Test Definition Format) entries for deterministic testing.

All entries must be valid against STEP_SCHEMA.
Library mode selects from these — the same TDF name always produces the same workflow.
Add new entries here when you need a new canonical test workflow.
"""
from typing import Any, Dict

_LIBRARY: Dict[str, Dict[str, Any]] = {
    "simple_distribution": {
        "name": "simple_distribution",
        "description": "Pick up tips, distribute reagent into all wells of a 96-well plate, drop tips.",
        "steps": [
            {
                "id": "get_tips_0",
                "type": "get_tips",
                "tip_type": "DiTi_200uL",
            },
            {
                "id": "distribute_0",
                "type": "reagent_distribution",
                "volumes": [100],
                "labware_source": "Reagent_Trough_100mL",
                "labware_target": "Plate_96_Well",
                "tip_type": "DiTi_200uL",
                "liquid_class": "Buffer",
                "selected_wells_source": ["A1"],
                "selected_wells_target": ["A1-H12"],
            },
            {
                "id": "drop_tips_0",
                "type": "drop_tips_to_location",
                "labware": "Waste_Container",
            },
        ],
    },

    "distribution_with_incubation": {
        "name": "distribution_with_incubation",
        "description": "Distribute reagent then incubate the plate at 37 °C for 30 minutes.",
        "steps": [
            {
                "id": "get_tips_0",
                "type": "get_tips",
                "tip_type": "DiTi_200uL",
            },
            {
                "id": "distribute_0",
                "type": "reagent_distribution",
                "volumes": [50],
                "labware_source": "Reagent_Trough_100mL",
                "labware_target": "Plate_96_Well",
                "tip_type": "DiTi_200uL",
                "liquid_class": "Buffer",
                "selected_wells_source": ["A1"],
                "selected_wells_target": ["A1-H12"],
            },
            {
                "id": "drop_tips_0",
                "type": "drop_tips_to_location",
                "labware": "Waste_Container",
            },
            {
                "id": "incubate_0",
                "type": "incubate",
                "duration_seconds": 1800,
                "temperature_celsius": 37.0,
                "device": "Heated_Incubator",
            },
        ],
    },

    "distribution_mix_incubate": {
        "name": "distribution_mix_incubate",
        "description": "Distribute reagent, mix wells 5×, drop tips, then incubate 1 hour at 37 °C.",
        "steps": [
            {
                "id": "get_tips_0",
                "type": "get_tips",
                "tip_type": "DiTi_200uL",
            },
            {
                "id": "distribute_0",
                "type": "reagent_distribution",
                "volumes": [100],
                "labware_source": "Reagent_Trough_100mL",
                "labware_target": "Plate_96_Well",
                "tip_type": "DiTi_200uL",
                "liquid_class": "Buffer",
                "selected_wells_source": ["A1"],
                "selected_wells_target": ["A1-H12"],
            },
            {
                "id": "mix_0",
                "type": "mix_volume",
                "volumes": [80],
                "labware": "Plate_96_Well",
                "liquid_class": "Buffer",
                "cycles": 5,
            },
            {
                "id": "drop_tips_0",
                "type": "drop_tips_to_location",
                "labware": "Waste_Container",
            },
            {
                "id": "incubate_0",
                "type": "incubate",
                "duration_seconds": 3600,
                "temperature_celsius": 37.0,
                "device": "Heated_Incubator",
            },
        ],
    },
}


def list_tdf_names() -> list:
    """List available TDF names in the library."""
    return list(_LIBRARY.keys())


def get_tdf(name: str) -> Dict[str, Any]:
    """Retrieve a TDF by name. Raises KeyError if not found."""
    if name not in _LIBRARY:
        available = ", ".join(sorted(_LIBRARY.keys()))
        raise KeyError(
            f"TDF '{name}' not found in library. Available: {available}"
        )
    return _LIBRARY[name]
