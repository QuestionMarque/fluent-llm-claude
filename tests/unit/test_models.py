import pytest
from execution_engine.models.workflow import Step, Workflow, STEP_SCHEMA
from execution_engine.models.runtime_call import RuntimeCall
from execution_engine.models.state import State
from execution_engine.models.feedback import FeedbackItem, ValidationFeedback


class TestStepSchema:
    def test_all_entries_have_required_and_optional(self):
        for step_type, schema in STEP_SCHEMA.items():
            assert "required" in schema, f"{step_type} missing 'required'"
            assert "optional" in schema, f"{step_type} missing 'optional'"
            assert isinstance(schema["required"], list)
            assert isinstance(schema["optional"], list)

    def test_reagent_distribution_required_fields(self):
        schema = STEP_SCHEMA["reagent_distribution"]
        for field in ("volumes", "labware_source", "labware_target"):
            assert field in schema["required"]

    def test_mix_volume_optional_cycles(self):
        assert "cycles" in STEP_SCHEMA["mix_volume"]["optional"]

    def test_get_tips_required_tip_type(self):
        assert "diti_type" in STEP_SCHEMA["get_tips"]["required"]

    def test_transfer_labware_required_fields(self):
        schema = STEP_SCHEMA["transfer_labware"]
        assert "labware_name" in schema["required"]
        assert "target_location" in schema["required"]

    def test_all_expected_step_types_exist(self):
        expected = {
            "reagent_distribution", "sample_transfer",
            "aspirate_volume", "dispense_volume", "mix_volume",
            "transfer_labware", "get_tips",
            "drop_tips_to_location", "empty_tips",
        }
        assert expected.issubset(STEP_SCHEMA.keys())

    def test_distribution_tip_fields_are_required(self):
        for step_type in ("reagent_distribution", "sample_transfer"):
            required = STEP_SCHEMA[step_type]["required"]
            assert "DiTi_type" in required


class TestStep:
    def test_defaults(self):
        step = Step(type="incubate")
        assert step.params == {}
        assert step.id is None

    def test_with_params_and_id(self):
        step = Step(type="get_tips", params={"diti_type": "DiTi_200uL"}, id="step_0")
        assert step.params["diti_type"] == "DiTi_200uL"
        assert step.id == "step_0"


class TestRuntimeCall:
    def test_defaults(self):
        call = RuntimeCall(method_name="GetTips")
        assert call.method_name == "GetTips"
        assert call.variables == {}
        assert call.step_id is None

    def test_with_variables_and_step_id(self):
        call = RuntimeCall(
            method_name="ReagentDistribution",
            variables={"volumes": [100]},
            step_id="s0",
        )
        assert call.variables["volumes"] == [100]
        assert call.step_id == "s0"


class TestWorkflow:
    def test_defaults(self):
        wf = Workflow()
        assert wf.steps == []
        assert wf.metadata == {}

    def test_with_steps(self):
        steps = [Step(type="get_tips", params={"diti_type": "DiTi_200uL"})]
        wf = Workflow(steps=steps, metadata={"name": "test"})
        assert len(wf.steps) == 1
        assert wf.metadata["name"] == "test"


class TestState:
    def test_initial_values(self):
        s = State()
        assert s.tip_loaded is False
        assert s.well_volumes == {}
        assert s.execution_history == []

    def test_tip_loading(self):
        s = State()
        s.load_tip()
        assert s.tip_loaded is True
        s.unload_tip()
        assert s.tip_loaded is False

    def test_add_volume(self):
        s = State()
        s.add_volume("A1", 100.0)
        s.add_volume("A1", 50.0)
        assert s.well_volumes["A1"] == 150.0

    def test_remove_volume(self):
        s = State()
        s.add_volume("B2", 100.0)
        s.remove_volume("B2", 40.0)
        assert s.well_volumes["B2"] == 60.0

    def test_remove_volume_floors_at_zero(self):
        s = State()
        s.add_volume("C3", 10.0)
        s.remove_volume("C3", 50.0)
        assert s.well_volumes["C3"] == 0.0


class TestValidationFeedback:
    def test_is_valid_when_no_errors(self):
        fb = ValidationFeedback()
        assert fb.is_valid is True

    def test_is_invalid_with_errors(self):
        fb = ValidationFeedback(errors=[FeedbackItem(type="test", message="bad")])
        assert fb.is_valid is False

    def test_warnings_do_not_affect_validity(self):
        fb = ValidationFeedback(
            warnings=[FeedbackItem(type="warn", message="note", severity="warning")]
        )
        assert fb.is_valid is True
