import json
from pathlib import Path

import pytest

from execution_engine.capability_registry.loader import load_default_registry
from execution_engine.models.workflow import STEP_SCHEMA, Workflow
from execution_engine.orchestration.execution_loop import ExecutionLoop, ExecutionLoopResult
from execution_engine.runtime.pyfluent_adapter import PyFluentAdapter
from execution_engine.validation.validator_wrapper import ValidatorWrapper
from execution_engine.workflow.decomposer import WorkflowDecomposer


IR_EXAMPLES_DIR = (
    Path(__file__).resolve().parents[2] / "execution_engine" / "orchestration" / "IR_examples"
)


def list_ir_names():
    return sorted(path.stem for path in IR_EXAMPLES_DIR.glob("*.json"))


def load_ir(name: str):
    file_path = IR_EXAMPLES_DIR / f"{name}.json"
    if not file_path.exists():
        raise KeyError(name)
    with open(file_path, "r") as f:
        return json.load(f)


class MockRuntime:
    def PrepareMethod(self, name): pass
    def SetVariableValue(self, name, value): pass
    def RunMethod(self): return "OK"


@pytest.fixture
def loop():
    registry = load_default_registry()
    return ExecutionLoop(
        registry=registry,
        runtime_adapter=PyFluentAdapter(runtime=MockRuntime()),
        validator=ValidatorWrapper(registry=registry),
        ir_mode="library",
        max_retries=1,
    )


class TestIRLibrary:
    def test_list_returns_non_empty(self):
        names = list_ir_names()
        assert len(names) >= 3

    def test_all_expected_names_present(self):
        names = list_ir_names()
        for expected in (
            "pipetting_cycle",
            "just_tips",
            "transfer_samples_plate_to_plate",
            "transfer_samples_tubes_to_plate",
            "dilute_samples_from_tube",
            "serial_dilution",
            "dilute_samples_from_full_plate",
            "sample_tube_to_plate_replicates",
            "fill_plate_hotel",
            "distribute_antisera",
            "distribute_antigens",
            "add_tRBC",
        ):
            assert expected in names, f"Expected IR '{expected}' not found in library"

    def test_get_ir_returns_dict_with_steps(self):
        ir = load_ir("pipetting_cycle")
        assert isinstance(ir, dict)
        assert "steps" in ir
        assert len(ir["steps"]) > 0

    def test_get_unknown_ir_raises_key_error(self):
        with pytest.raises(KeyError):
            load_ir("this_does_not_exist")

    def test_all_library_irs_have_valid_step_types(self):
        for name in list_ir_names():
            ir = load_ir(name)
            for step in ir["steps"]:
                assert step["type"] in STEP_SCHEMA, (
                    f"IR '{name}' step '{step.get('id')}' has unknown type '{step['type']}'"
                )

    def test_all_library_irs_have_non_empty_steps(self):
        for name in list_ir_names():
            ir = load_ir(name)
            assert len(ir["steps"]) > 0, f"'{name}' has no steps"

    def test_serial_dilution_has_many_steps(self):
        ir = load_ir("serial_dilution")
        assert isinstance(ir, dict)
        assert len(ir["steps"]) > 10

    def test_distribute_antigens_has_dispense_steps(self):
        ir = load_ir("distribute_antigens")
        dispense_count = sum(1 for s in ir["steps"] if s["type"] == "dispense_volume")
        assert dispense_count == 12  # one per column


class TestExecutionLoop:
    @pytest.mark.parametrize("ir_name", ["pipetting_cycle", "just_tips"])
    def test_known_ir_succeeds(self, loop, ir_name):
        result = loop.run(ir_name=ir_name)
        assert result.success
        assert result.attempts == 1

    def test_just_tips_succeeds(self, loop):
        result = loop.run(ir_name="just_tips")
        assert result.success

    def test_unknown_ir_name_returns_failure(self, loop):
        result = loop.run(ir_name="nonexistent_workflow")
        assert not result.success
        assert result.error is not None

    def test_result_contains_runtime_calls_and_log(self, loop):
        result = loop.run(ir_name="pipetting_cycle")
        assert len(result.runtime_calls) > 0
        assert len(result.execution_log) > 0

    def test_result_contains_state(self, loop):
        result = loop.run(ir_name="pipetting_cycle")
        assert result.state is not None

    def test_result_contains_validation_feedback(self, loop):
        result = loop.run(ir_name="pipetting_cycle")
        assert result.validation_feedback is not None
        assert result.validation_feedback.is_valid
