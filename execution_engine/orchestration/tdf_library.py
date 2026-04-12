"""TDF library — pre-defined workflows for deterministic library-mode execution.

Two storage formats are supported:

Dict TDFs (legacy / schema-validated path):
  Stored in _DICT_LIBRARY.  The execution loop decomposes these with
  WorkflowDecomposer and runs them through full schema + semantic validation.
  Validation failures are fatal in library mode (fail-fast).

Workflow TDFs (trusted developer path):
  Stored in _WORKFLOW_LIBRARY as pre-built Workflow objects.
  The execution loop skips decomposition and schema validation for these —
  they are trusted developer-authored objects.  Semantic (registry) checks
  still run advisory-only.  This format supports extended field names and
  step types that aren't in the strict dict-format STEP_SCHEMA.

get_tdf(name) returns either a dict or a Workflow.
The execution loop checks isinstance(result, Workflow) to choose the path.
"""
from typing import Any, Dict, Union

from ..models.workflow import Workflow, Step


# ---------------------------------------------------------------------------
# Dict-format TDFs (legacy, fully schema-validated)
# ---------------------------------------------------------------------------
_DICT_LIBRARY: Dict[str, Dict[str, Any]] = {
    "simple_distribution_dict": {
        "name": "simple_distribution_dict",
        "description": "Pick up tips → distribute → drop tips (dict format, schema-validated).",
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

    "distribution_with_incubation_dict": {
        "name": "distribution_with_incubation_dict",
        "description": "Distribute then incubate (dict format).",
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

    "distribution_mix_incubate_dict": {
        "name": "distribution_mix_incubate_dict",
        "description": "Distribute → mix → drop tips → incubate (dict format).",
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


# ---------------------------------------------------------------------------
# Workflow-format TDFs (trusted developer objects — extended field support)
# ---------------------------------------------------------------------------

def _simple_distribution() -> Workflow:
    return Workflow(
        steps=[
            Step(
                type="reagent_distribution",
                params={
                    "volume_uL": 50,
                    "liquid": "DPBS",
                    "liquid_class": "Water_Free",
                    "tip_type": "FCA_DiTi_200uL",
                    "source": "Trough_25mL:A1",
                    "target": "Plate_96:A1",
                },
            )
        ]
    )


def _distribution_with_incubation() -> Workflow:
    return Workflow(
        steps=[
            Step(
                type="reagent_distribution",
                params={
                    "volume_uL": 30,
                    "liquid": "DPBS",
                    "liquid_class": "Water_Free",
                    "tip_type": "FCA_DiTi_50uL",
                    "source": "Trough_25mL:A1",
                    "target": "Plate_96:B1",
                },
            ),
            Step(
                type="incubate",
                params={
                    "time_s": 300,
                    "location": "Heated_Incubator",
                    "labware": "Plate_96",
                },
            ),
        ]
    )


def _distribution_mix_incubate() -> Workflow:
    return Workflow(
        steps=[
            Step(
                type="reagent_distribution",
                params={
                    "volume_uL": 20,
                    "liquid": "DPBS",
                    "liquid_class": "Water_Free",
                    "tip_type": "FCA_DiTi_50uL",
                    "source": "Trough_25mL:A1",
                    "target": "Plate_96:C1",
                },
            ),
            Step(
                type="mix",
                params={
                    "volume_uL": 15,
                    "cycles": 3,
                    "target": "Plate_96:C1",
                    "liquid_class": "Water_Free",
                    "tip_type": "FCA_DiTi_50uL",
                },
            ),
            Step(
                type="incubate",
                params={
                    "time_s": 600,
                    "location": "Heated_Incubator",
                    "labware": "Plate_96",
                },
            ),
        ]
    )


def _just_tips() -> Workflow:
    return Workflow(
        steps=[
            Step(
                type="get_tips",
                params={
                    "diti_type": "FCA_DiTi_200uL",
                    "airgap_volume": 70,
                    "airgap_speed": 100,
                    "tip_indices": [0, 1, 2, 3, 4, 5, 6, 7],
                },
            ),
        ]
    )


def _transfer_samples_plate_to_plate() -> Workflow:
    return Workflow(
        steps=[
            Step(
                type="get_tips",
                params={"diti_type": "FCA_DiTi_200uL"},
            ),
            Step(
                type="aspirate_volume",
                params={
                    "volumes": 50,
                    "labware": "sample_plate",
                    "liquid_class": "Water_Free_Single",
                    "well_offsets": [0, 1, 2, 3, 4, 5, 6, 7],
                    "tip_indices": [0, 1, 2, 3, 4, 5, 6, 7],
                },
            ),
            Step(
                type="dispense_volume",
                params={
                    "volumes": 50,
                    "labware": "dilution_plate",
                    "liquid_class": "Water_Free_Single",
                    "well_offsets": [0, 1, 2, 3, 4, 5, 6, 7],
                    "tip_indices": [0, 1, 2, 3, 4, 5, 6, 7],
                },
            ),
            Step(
                type="drop_tips_to_location",
                params={"labware": "DiTi_waste"},
            ),
        ]
    )


def _transfer_samples_tubes_to_plate() -> Workflow:
    return Workflow(
        steps=[
            Step(
                type="get_tips",
                params={"diti_type": "FCA_DiTi_200uL"},
            ),
            Step(
                type="aspirate_volume",
                params={
                    "volumes": 100,
                    "labware": "tube_runner",
                    "liquid_class": "Water_Free_Single",
                    "well_offset": list(range(8)),
                },
            ),
            Step(
                type="dispense_volume",
                params={
                    "volumes": 100,
                    "labware": "dilution_plate",
                    "liquid_class": "Water_Free_Single",
                    "well_offset": list(range(8)),
                },
            ),
            Step(
                type="drop_tips_to_location",
                params={"labware": "DiTi_waste"},
            ),
        ]
    )


def _dilute_samples_from_tube() -> Workflow:
    return Workflow(
        steps=[
            Step(type="get_tips", params={"diti_type": "FCA_DiTi_200uL"}),
            Step(
                type="aspirate_volume",
                params={
                    "volumes": 100,
                    "labware": "diluent_reservoir",
                    "liquid_class": "Water_Free_Multi",
                },
            ),
            Step(
                type="dispense_volume",
                params={
                    "volumes": 50,
                    "labware": "dilution_plate",
                    "liquid_class": "Water_Free_Multi",
                    "well_offset": list(range(8)),
                },
            ),
            Step(
                type="dispense_volume",
                params={
                    "volumes": 50,
                    "labware": "dilution_plate",
                    "liquid_class": "Water_Free_Multi",
                    "well_offset": list(range(8, 16)),
                },
            ),
            Step(type="drop_tips_to_location", params={"labware": "DiTi_waste"}),
            Step(type="get_tips", params={"diti_type": "FCA_DiTi_200uL"}),
            Step(
                type="aspirate_volume",
                params={
                    "volumes": 50,
                    "labware": "tube_runner",
                    "liquid_class": "Water_Free_Single",
                    "well_offset": list(range(8)),
                },
            ),
            Step(
                type="dispense_volume",
                params={
                    "volumes": 50,
                    "labware": "dilution_plate",
                    "liquid_class": "Water_Free_Single",
                    "well_offset": list(range(8)),
                },
            ),
            Step(type="drop_tips_to_location", params={"labware": "DiTi_waste"}),
            Step(type="get_tips", params={"diti_type": "FCA_DiTi_200uL"}),
            Step(
                type="aspirate_volume",
                params={
                    "volumes": 50,
                    "labware": "tube_runner",
                    "liquid_class": "Water_Free_Single",
                    "well_offset": list(range(8, 16)),
                },
            ),
            Step(
                type="dispense_volume",
                params={
                    "volumes": 50,
                    "labware": "dilution_plate",
                    "liquid_class": "Water_Free_Single",
                    "well_offset": list(range(8, 16)),
                },
            ),
            Step(type="drop_tips_to_location", params={"labware": "DiTi_waste"}),
        ]
    )


def _serial_dilution() -> Workflow:
    """10-step serial dilution across 96-well plate columns (8 wells per column)."""
    steps = [Step(type="get_tips", params={"diti_type": "FCA_DiTi_200uL"})]
    col_size = 8
    n_transfers = 10  # columns 0→1 through 9→10
    for col in range(n_transfers):
        src = list(range(col * col_size, (col + 1) * col_size))
        dst = list(range((col + 1) * col_size, (col + 2) * col_size))
        steps += [
            Step(
                type="aspirate_volume",
                params={
                    "volumes": 25,
                    "labware": "dilution_plate",
                    "liquid_class": "Water_Free_Single",
                    "well_offset": src,
                },
            ),
            Step(
                type="dispense_volume",
                params={
                    "volumes": 25,
                    "labware": "dilution_plate",
                    "liquid_class": "Water_Free_Single",
                    "well_offset": dst,
                },
            ),
            Step(
                type="mix_volume",
                params={
                    "volumes": 40,
                    "labware": "dilution_plate",
                    "liquid_class": "Water_Free_Mix",
                    "well_offsets": dst,
                    "cycles": 2,
                },
            ),
            Step(
                type="empty_tips",
                params={
                    "labware": "dilution_plate",
                    "liquid_class": "Empty Tip",
                    "well_offsets": dst,
                },
            ),
        ]
    # Final aspirate + drop after last transfer
    last_src = list(range(n_transfers * col_size, (n_transfers + 1) * col_size))
    steps += [
        Step(
            type="aspirate_volume",
            params={
                "volumes": 25,
                "labware": "dilution_plate",
                "liquid_class": "Water_Free_Single",
                "well_offset": last_src,
            },
        ),
        Step(type="drop_tips_to_location", params={"labware": "DiTi_waste"}),
    ]
    return Workflow(steps=steps)


def _dilute_samples_from_full_plate() -> Workflow:
    return Workflow(
        steps=[
            Step(
                type="reagent_distribution",
                params={
                    "labware_empty_tips": "diluent_trough",
                    "volumes": 25,
                    "sample_count": 96,
                    "DiTi_type": "FCA_DiTi_1000uL",
                    "DiTi_waste": "DiTi_waste",
                    "labware_source": "diluent_trough",
                    "labware_target": "dilution_plate",
                    "selected_wells_source": 0,
                    "selected_wells_target": list(range(96)),
                    "liquid_class": "Water_Free_Multi",
                },
            ),
            Step(
                type="sample_transfer",
                params={
                    "labware_empty_tips": "Liquid_waste",
                    "volumes": 25,
                    "sample_count": 96,
                    "DiTi_type": "FCA_DiTi_200uL",
                    "DiTi_waste": "DiTi_waste",
                    "labware_source": "sample_plate",
                    "labware_target": "dilution_plate",
                    "selected_wells_source": list(range(96)),
                    "selected_wells_target": list(range(96)),
                    "liquid_class": "Water_Free_Single",
                    "tips_per_well_source": 1,
                },
            ),
        ]
    )


def _sample_tube_to_plate_replicates() -> Workflow:
    return Workflow(
        steps=[
            Step(
                type="sample_transfer",
                params={
                    "labware_empty_tips": "Liquid_waste",
                    "volumes": 50,
                    "sample_count": 16,
                    "DiTi_type": "FCA_DiTi_10000uL",
                    "DiTi_waste": "DiTi_waste",
                    "labware_source": "tube_runner",
                    "labware_target": "dilution_plate",
                    "selected_wells_source": list(range(16)),
                    "selected_wells_target": list(range(96)),
                    "liquid_class": "Water_Free_Multi",
                    "sample_direction": "ColumnWise",
                    "number_replicates": 3,
                    "replicate_direction": "RowWise",
                    "tips_per_well_source": 1,
                },
            )
        ]
    )


def _fill_plate_hotel() -> Workflow:
    return Workflow(
        steps=[
            Step(
                type="transfer_labware",
                params={
                    "labware_name": "96_plate",
                    "target_location": "Nest_61mm",
                    "target_position": 1,
                },
            ),
            Step(
                type="reagent_distribution",
                params={
                    "labware_empty_tips": "Liquid_waste",
                    "volumes": 50,
                    "sample_count": 16,
                    "DiTi_type": "FCA_DiTi_1000uL",
                    "DiTi_waste": "DiTi_waste",
                    "labware_source": "reagentA",
                    "labware_target": "96_plate",
                    "selected_wells_source": 0,
                    "selected_wells_target": list(range(96)),
                    "liquid_class": "Water_Free_Multi",
                },
            ),
            Step(type="get_tips", params={"diti_type": "FCA_DiTi_200uL"}),
            Step(
                type="aspirate_volume",
                params={
                    "volumes": 50,
                    "labware": "sample_tubes",
                    "liquid_class": "Water_Free_Single",
                    "well_offset": [0, 1, 2, 3, 4, 5, 6, 7],
                },
            ),
            Step(
                type="dispense_volume",
                params={
                    "volumes": 50,
                    "labware": "96_plate",
                    "liquid_class": "Water_Free_Single",
                    "well_offset": [0, 1, 2, 3, 4, 5, 6, 7],
                },
            ),
            Step(type="drop_tips_to_location", params={"labware": "DiTi_waste"}),
            Step(type="get_tips", params={"diti_type": "FCA_DiTi_200uL"}),
            Step(
                type="aspirate_volume",
                params={
                    "volumes": 50,
                    "labware": "sample_tubes",
                    "liquid_class": "Water_Free_Single",
                    "well_offset": [8, 9, 10, 11, 12, 13, 14, 15],
                },
            ),
            Step(
                type="dispense_volume",
                params={
                    "volumes": 50,
                    "labware": "96_plate",
                    "liquid_class": "Water_Free_Single",
                    "well_offset": [8, 9, 10, 11, 12, 13, 14, 15],
                },
            ),
            Step(type="drop_tips_to_location", params={"labware": "DiTi_waste"}),
            Step(
                type="transfer_labware",
                params={
                    "labware_name": "96_plate",
                    "target_location": "Hotel",
                    "target_position": 1,
                },
            ),
        ]
    )


def _distribute_antisera() -> Workflow:
    return Workflow(
        steps=[
            Step(
                type="get_tips",
                params={
                    "diti_type": "FCA_DiTi_200uL",
                    "tip_indices": list(range(8)),
                },
            ),
            Step(
                type="aspirate_volume",
                params={
                    "volumes": [50] * 4,
                    "labware": "Antisera_1",
                    "liquid_class": "LIQ_CLASS_ANTISERA",
                    "well_offsets": list(range(4)),
                    "tip_indices": list(range(4)),
                },
            ),
            Step(
                type="aspirate_volume",
                params={
                    "volumes": [0] * 4 + [50] * 4,
                    "labware": "Antisera_2",
                    "liquid_class": "LIQ_CLASS_ANTISERA",
                    "well_offsets": list(range(4)),
                    "tip_indices": list(range(4, 8)),
                },
            ),
            Step(
                type="dispense_volume",
                params={
                    "volumes": [50] * 8,
                    "labware": "plate_96",
                    "liquid_class": "LIQ_CLASS_ANTISERA",
                    "well_offsets": list(range(8)),
                    "tip_indices": list(range(8)),
                },
            ),
            Step(type="drop_tips_to_location", params={"labware": "DiTi_waste"}),
        ]
    )


def _distribute_antigens() -> Workflow:
    dispense_steps = [
        Step(
            type="dispense_volume",
            params={
                "volumes": [25] * 8,
                "labware": "plate",
                "liquid_class": "LIQ_CLASS_ANTIGEN",
                "well_offsets": list(range(col * 8, (col + 1) * 8)),
                "tip_indices": list(range(8)),
            },
        )
        for col in range(12)
    ]
    return Workflow(
        steps=[
            Step(
                type="get_tips",
                params={
                    "diti_type": "FCA_DiTi_1000uL",
                    "tip_indices": list(range(8)),
                },
            ),
            Step(
                type="aspirate_volume",
                params={
                    "volumes": [25 * 12] * 8,
                    "labware": "LABWARE_ANTIGEN_A",
                    "liquid_class": "LIQ_CLASS_ANTIGEN",
                    "well_offsets": [0] * 8,
                    "tip_indices": list(range(8)),
                },
            ),
            *dispense_steps,
            Step(
                type="empty_tips",
                params={
                    "labware": "LABWARE_ANTIGEN_A",
                    "tip_indices": list(range(8)),
                },
            ),
            Step(
                type="drop_tips_to_location",
                params={
                    "labware": "DITI_WASTE",
                    "tip_indices": list(range(8)),
                },
            ),
        ]
    )


def _add_tRBC() -> Workflow:
    dispense_steps = [
        Step(
            type="dispense_volume",
            params={
                "volumes": [50] * 8,
                "labware": "plate",
                "liquid_class": "LIQ_CLASS_TRBC",
                "well_offsets": list(range(col * 8, (col + 1) * 8)),
                "tip_indices": list(range(8)),
            },
        )
        for col in range(12)
    ]
    return Workflow(
        steps=[
            Step(
                type="get_tips",
                params={
                    "diti_type": "FCA_DiTi_1000uL",
                    "tip_indices": list(range(8)),
                },
            ),
            Step(
                type="mix_volume",
                params={
                    "labware": "tRBC",
                    "volumes": 800,
                    "liquid_class": "Water Mix",
                    "cycles": 5,
                    "well_offsets": 0,
                },
            ),
            Step(
                type="empty_tips",
                params={"labware": "tRBC"},
            ),
            Step(
                type="aspirate_volume",
                params={
                    "volumes": [50 * 12] * 8,
                    "labware": "LABWARE_TRBC",
                    "liquid_class": "LIQ_CLASS_TRBC",
                    "well_offsets": [0] * 8,
                    "tip_indices": list(range(8)),
                },
            ),
            *dispense_steps,
            Step(
                type="empty_tips",
                params={"labware": "LABWARE_TRBC"},
            ),
            Step(
                type="drop_tips_to_location",
                params={
                    "labware": "DITI_WASTE",
                    "tip_indices": list(range(8)),
                },
            ),
        ]
    )


# Build the Workflow library at import time (functions called once)
_WORKFLOW_LIBRARY: Dict[str, Workflow] = {
    "simple_distribution":              _simple_distribution(),
    "distribution_with_incubation":     _distribution_with_incubation(),
    "distribution_mix_incubate":        _distribution_mix_incubate(),
    "just_tips":                        _just_tips(),
    "transfer_samples_plate_to_plate":  _transfer_samples_plate_to_plate(),
    "transfer_samples_tubes_to_plate":  _transfer_samples_tubes_to_plate(),
    "dilute_samples_from_tube":         _dilute_samples_from_tube(),
    "serial_dilution":                  _serial_dilution(),
    "dilute_samples_from_full_plate":   _dilute_samples_from_full_plate(),
    "sample_tube_to_plate_replicates":  _sample_tube_to_plate_replicates(),
    "fill_plate_hotel":                 _fill_plate_hotel(),
    "distribute_antisera":              _distribute_antisera(),
    "distribute_antigens":              _distribute_antigens(),
    "add_tRBC":                         _add_tRBC(),
}

# Unified lookup — Workflow entries take precedence over dict entries for shared names
_LIBRARY: Dict[str, Union[Dict[str, Any], Workflow]] = {
    **_DICT_LIBRARY,
    **_WORKFLOW_LIBRARY,
}


def list_tdf_names() -> list:
    """List all available TDF names (both dict and Workflow formats)."""
    return list(_LIBRARY.keys())


def get_tdf(name: str) -> Union[Dict[str, Any], Workflow]:
    """Retrieve a TDF by name.

    Returns either a dict (schema-validated path) or a Workflow object
    (trusted developer path).  The execution loop checks isinstance(result, Workflow)
    to select the appropriate code path.

    Raises KeyError if name is not found.
    """
    if name not in _LIBRARY:
        available = ", ".join(sorted(_LIBRARY.keys()))
        raise KeyError(
            f"TDF '{name}' not found in library. Available: {available}"
        )
    return _LIBRARY[name]
