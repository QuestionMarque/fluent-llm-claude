import json
from pathlib import Path

import pytest

from execution_engine.capability_registry.loader import load_default_registry
from execution_engine.models.workflow import STEP_SCHEMA, Workflow
from execution_engine.orchestration.execution_loop import (
    ExecutionLoop,
    ExecutionLoopResult,
    PreparedWorkflow,
    runtime_calls_to_dict_list,
)
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


class AsyncMockBackend:
    """Minimal async-shaped backend for orchestration tests."""

    def __init__(self):
        self.executed = []

    async def setup(self): pass

    async def stop(self): pass

    async def aspirate_volume(self, **kwargs):
        self.executed.append(("aspirate_volume", kwargs))

    async def dispense_volume(self, **kwargs):
        self.executed.append(("dispense_volume", kwargs))

    async def get_tips(self, **kwargs):
        self.executed.append(("get_tips", kwargs))

    async def drop_tips_to_location(self, **kwargs):
        self.executed.append(("drop_tips_to_location", kwargs))

    async def run_method(self, method_name, wait_for_completion=False, **kwargs):
        self.executed.append(("run_method", method_name, kwargs))

    async def wait_for_channel(self, timeout=90): pass


@pytest.fixture
def registry():
    return load_default_registry()


@pytest.fixture
def prepare_only_loop(registry):
    """Loop with no runtime adapter — suitable for testing prepare()."""
    return ExecutionLoop(
        registry=registry,
        validator=ValidatorWrapper(registry=registry),
        runtime_adapter=None,
        ir_mode="library",
        max_retries=1,
    )


@pytest.fixture
def loop(registry):
    """Loop wired to a mock async backend — suitable for testing run()."""
    backend = AsyncMockBackend()
    return ExecutionLoop(
        registry=registry,
        validator=ValidatorWrapper(registry=registry),
        runtime_adapter=PyFluentAdapter(backend=backend),
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


class TestPrepare:
    """The preparation phase is sync, backend-free, and returns a
    PreparedWorkflow with the RuntimeCalls that would be executed."""

    @pytest.mark.parametrize("ir_name", ["pipetting_cycle", "just_tips"])
    def test_known_ir_prepares_successfully(self, prepare_only_loop, ir_name):
        prepared = prepare_only_loop.prepare(ir_name=ir_name)
        assert isinstance(prepared, PreparedWorkflow)
        assert prepared.success
        assert prepared.attempts == 1
        assert len(prepared.runtime_calls) == len(prepared.workflow.steps)
        assert prepared.validation_feedback.is_valid

    def test_unknown_ir_name_fails_prepare(self, prepare_only_loop):
        prepared = prepare_only_loop.prepare(ir_name="does_not_exist")
        assert not prepared.success
        assert prepared.error is not None

    def test_prepare_does_not_require_runtime_adapter(self, prepare_only_loop):
        # prepare_only_loop is configured with runtime_adapter=None.
        prepared = prepare_only_loop.prepare(ir_name="pipetting_cycle")
        assert prepared.success

    def test_run_without_adapter_raises(self, prepare_only_loop):
        with pytest.raises(RuntimeError, match="runtime_adapter"):
            prepare_only_loop.run_sync(ir_name="pipetting_cycle")

    def test_runtime_calls_are_json_serializable(self, prepare_only_loop):
        prepared = prepare_only_loop.prepare(ir_name="pipetting_cycle")
        payload = runtime_calls_to_dict_list(prepared.runtime_calls)
        # Round-trip through JSON — proves the portable format is real.
        reloaded = json.loads(json.dumps(payload))
        assert reloaded == payload
        assert all("method_name" in entry for entry in reloaded)
        assert all("variables" in entry for entry in reloaded)


class TestExecutionLoop:
    @pytest.mark.parametrize("ir_name", ["pipetting_cycle", "just_tips"])
    def test_known_ir_succeeds(self, loop, ir_name):
        result = loop.run_sync(ir_name=ir_name)
        assert result.success
        assert result.attempts == 1

    def test_just_tips_succeeds(self, loop):
        result = loop.run_sync(ir_name="just_tips")
        assert result.success

    def test_unknown_ir_name_returns_failure(self, loop):
        result = loop.run_sync(ir_name="nonexistent_workflow")
        assert not result.success
        assert result.error is not None

    def test_result_contains_runtime_calls_and_log(self, loop):
        result = loop.run_sync(ir_name="pipetting_cycle")
        assert len(result.runtime_calls) > 0
        assert len(result.execution_log) > 0

    def test_result_contains_state(self, loop):
        result = loop.run_sync(ir_name="pipetting_cycle")
        assert result.state is not None

    def test_result_contains_validation_feedback(self, loop):
        result = loop.run_sync(ir_name="pipetting_cycle")
        assert result.validation_feedback is not None
        assert result.validation_feedback.is_valid
