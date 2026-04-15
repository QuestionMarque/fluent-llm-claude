import pytest

from execution_engine.capability_registry.loader import load_default_registry
from execution_engine.mapper.step_mapper import StepMapper, MapperError
from execution_engine.mapper.variable_mapper import VariableMapper
from execution_engine.models.runtime_call import RuntimeCall
from execution_engine.models.workflow import Step, Workflow


@pytest.fixture
def registry():
    return load_default_registry()


@pytest.fixture
def mapper(registry):
    return StepMapper(registry)


class TestStepMapper:
    def test_reagent_distribution_maps_to_registry_method(self, mapper):
        step = Step(type="reagent_distribution", params={
            "volumes": [100],
            "labware_source": "Reagent_Trough_100mL",
            "labware_target": "Plate_96_Well",
            "tip_type": "DiTi_200uL",
            "liquid_class": "Buffer",
        })
        call = mapper.map(step)
        assert isinstance(call, RuntimeCall)
        assert call.method_name == "ReagentDistribution"
        assert call.variables["tip_type"] == "DiTi_200uL"
        assert call.variables["labware_source"] == "Reagent_Trough_100mL"

    def test_get_tips_maps_to_get_tips_method(self, mapper):
        step = Step(type="get_tips", params={"tip_type": "DiTi_200uL"}, id="s0")
        call = mapper.map(step)
        assert call.method_name == "GetTips"
        assert call.step_id == "s0"

    def test_transfer_labware_maps_to_transfer_labware_method(self, mapper):
        step = Step(type="transfer_labware", params={
            "labware_name": "Plate_96_Well",
            "target_location": "Slot_3",
        })
        call = mapper.map(step)
        assert call.method_name == "TransferLabware"

    def test_unknown_step_type_raises(self, mapper):
        step = Step(type="teleport_sample", params={})
        with pytest.raises(MapperError):
            mapper.map(step)

    def test_map_workflow_maps_every_step(self, mapper):
        workflow = Workflow(steps=[
            Step(type="get_tips", params={"tip_type": "DiTi_200uL"}, id="s0"),
            Step(type="reagent_distribution", params={
                "volumes": [100],
                "labware_source": "Reagent_Trough_100mL",
                "labware_target": "Plate_96_Well",
            }, id="s1"),
            Step(type="drop_tips_to_location", params={"labware": "Waste_Container"}, id="s2"),
        ])
        calls = mapper.map_workflow(workflow)
        assert [c.method_name for c in calls] == ["GetTips", "ReagentDistribution", "DropTipsToLocation"]
        assert [c.step_id for c in calls] == ["s0", "s1", "s2"]

    def test_runtime_call_has_no_score_field(self, mapper):
        """Sanity check: the decision-making fields are gone."""
        step = Step(type="get_tips", params={"tip_type": "DiTi_200uL"})
        call = mapper.map(step)
        assert not hasattr(call, "score")
        assert not hasattr(call, "reasoning")


class TestVariableMapper:
    def setup_method(self):
        self.mapper = VariableMapper()

    def test_distribution_maps_tip_alias(self):
        step = Step(type="reagent_distribution", params={
            "volumes": [100],
            "DiTi_type": "DiTi_200uL",
            "liquid_class": "Buffer",
            "labware_source": "Reagent_Trough_100mL",
            "labware_target": "Plate_96_Well",
        })
        variables = self.mapper.map(step)
        assert variables["tip_type"] == "DiTi_200uL"
        assert variables["labware_source"] == "Reagent_Trough_100mL"

    def test_mix_volume_includes_cycles(self):
        step = Step(type="mix_volume", params={
            "volumes": [80], "labware": "Plate_96_Well", "cycles": 5,
        })
        variables = self.mapper.map(step)
        assert variables["cycles"] == 5

    def test_mix_volume_without_cycles_omits_key(self):
        step = Step(type="mix_volume", params={"volumes": [80], "labware": "Plate_96_Well"})
        variables = self.mapper.map(step)
        assert "cycles" not in variables

    def test_transfer_labware_mapping(self):
        step = Step(type="transfer_labware", params={
            "labware_name": "Plate_96_Well",
            "target_location": "Slot_3",
            "target_position": 1,
        })
        variables = self.mapper.map(step)
        assert variables["labware_name"] == "Plate_96_Well"
        assert variables["target_location"] == "Slot_3"
        assert variables["target_position"] == 1

    def test_get_tips_normalizes_diti_type(self):
        step = Step(type="get_tips", params={"diti_type": "DiTi_1000uL"})
        variables = self.mapper.map(step)
        assert variables["tip_type"] == "DiTi_1000uL"

    def test_none_values_are_not_included(self):
        step = Step(type="get_tips", params={
            "tip_type": "DiTi_200uL",
            "airgap_volume": None,
        })
        variables = self.mapper.map(step)
        assert "airgap_volume" not in variables

    def test_well_offset_alias_normalized(self):
        step = Step(type="aspirate_volume", params={
            "volumes": [50], "labware": "Plate_96_Well", "well_offset": "A1",
        })
        variables = self.mapper.map(step)
        assert variables.get("well_offsets") == "A1"


class TestRegistryInvariant:
    """Every step type the system knows must have exactly one supporting method."""

    def test_every_step_type_has_one_method(self, registry):
        from execution_engine.models.workflow import STEP_SCHEMA
        for step_type in STEP_SCHEMA.keys():
            methods = registry.methods_supporting(step_type)
            assert len(methods) == 1, (
                f"Step type '{step_type}' has {len(methods)} methods supporting it "
                f"— expected exactly 1. Mapping would be ambiguous."
            )
