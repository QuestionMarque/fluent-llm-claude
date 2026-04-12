import pytest
from execution_engine.orchestration.execution_loop import ExecutionLoop, ExecutionLoopResult
from execution_engine.orchestration import ir_library
from execution_engine.models.workflow import Workflow, STEP_SCHEMA
from execution_engine.capability_registry.loader import load_default_registry
from execution_engine.validation.validator_wrapper import ValidatorWrapper
from execution_engine.planner.planner import Planner
from execution_engine.runtime.pyfluent_adapter import PyFluentAdapter
from execution_engine.workflow.decomposer import WorkflowDecomposer


class MockRuntime:
    def PrepareMethod(self, name): pass
    def SetVariableValue(self, name, value): pass
    def RunMethod(self): return "OK"


@pytest.fixture
def loop():
    registry = load_default_registry()
    return ExecutionLoop(
        planner=Planner(registry=registry),
        runtime_adapter=PyFluentAdapter(runtime=MockRuntime()),
        validator=ValidatorWrapper(registry=registry),
        ir_mode="library",
        max_retries=1,
    )


class TestIRLibrary:
    def test_list_returns_non_empty(self):
        names = ir_library.list_ir_names()
        assert len(names) >= 3

    def test_all_expected_names_present(self):
        names = ir_library.list_ir_names()
        for expected in (
            "simple_distribution",
            "distribution_with_incubation",
            "distribution_mix_incubate",
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

    def test_dict_irs_present(self):
        names = ir_library.list_ir_names()
        for expected in (
            "simple_distribution_dict",
            "distribution_with_incubation_dict",
            "distribution_mix_incubate_dict",
        ):
            assert expected in names

    def test_get_dict_ir_returns_dict_with_steps(self):
        ir = ir_library.get_ir("simple_distribution_dict")
        assert isinstance(ir, dict)
        assert "steps" in ir
        assert len(ir["steps"]) > 0

    def test_get_workflow_ir_returns_workflow(self):
        ir = ir_library.get_ir("simple_distribution")
        assert isinstance(ir, Workflow)
        assert len(ir.steps) > 0

    def test_get_unknown_ir_raises_key_error(self):
        with pytest.raises(KeyError):
            ir_library.get_ir("this_does_not_exist")

    def test_all_library_irs_have_valid_step_types(self):
        for name in ir_library.list_ir_names():
            ir = ir_library.get_ir(name)
            if isinstance(ir, Workflow):
                for step in ir.steps:
                    assert step.type in STEP_SCHEMA, (
                        f"IR '{name}' step '{step.id}' has unknown type '{step.type}'"
                    )
            else:
                for step in ir["steps"]:
                    assert step["type"] in STEP_SCHEMA, (
                        f"IR '{name}' step '{step.get('id')}' has unknown type '{step['type']}'"
                    )

    def test_workflow_irs_have_non_empty_steps(self):
        workflow_names = [
            "simple_distribution", "distribution_mix_incubate",
            "serial_dilution", "distribute_antigens", "add_tRBC",
        ]
        for name in workflow_names:
            ir = ir_library.get_ir(name)
            assert isinstance(ir, Workflow)
            assert len(ir.steps) > 0, f"'{name}' has no steps"

    def test_serial_dilution_has_many_steps(self):
        ir = ir_library.get_ir("serial_dilution")
        assert isinstance(ir, Workflow)
        # 1 get_tips + 10 * 4 (aspirate/dispense/mix/empty) + 1 aspirate + 1 drop = 43
        assert len(ir.steps) > 10

    def test_distribute_antigens_has_dispense_steps(self):
        ir = ir_library.get_ir("distribute_antigens")
        assert isinstance(ir, Workflow)
        dispense_count = sum(1 for s in ir.steps if s.type == "dispense_volume")
        assert dispense_count == 12  # one per column


class TestExecutionLoop:
    def test_simple_distribution_dict_succeeds(self, loop):
        result = loop.run(ir_name="simple_distribution_dict")
        assert result.success
        assert result.attempts == 1

    def test_distribution_mix_incubate_dict_succeeds(self, loop):
        result = loop.run(ir_name="distribution_mix_incubate_dict")
        assert result.success

    def test_distribution_with_incubation_dict_succeeds(self, loop):
        result = loop.run(ir_name="distribution_with_incubation_dict")
        assert result.success

    def test_simple_distribution_workflow_succeeds(self, loop):
        result = loop.run(ir_name="simple_distribution")
        assert result.success
        assert result.attempts == 1

    def test_distribution_mix_incubate_workflow_succeeds(self, loop):
        result = loop.run(ir_name="distribution_mix_incubate")
        assert result.success

    def test_distribution_with_incubation_workflow_succeeds(self, loop):
        result = loop.run(ir_name="distribution_with_incubation")
        assert result.success

    def test_just_tips_succeeds(self, loop):
        result = loop.run(ir_name="just_tips")
        assert result.success

    def test_serial_dilution_succeeds(self, loop):
        result = loop.run(ir_name="serial_dilution")
        assert result.success

    def test_distribute_antigens_succeeds(self, loop):
        result = loop.run(ir_name="distribute_antigens")
        assert result.success

    def test_add_tRBC_succeeds(self, loop):
        result = loop.run(ir_name="add_tRBC")
        assert result.success

    def test_unknown_ir_name_returns_failure(self, loop):
        result = loop.run(ir_name="nonexistent_workflow")
        assert not result.success
        assert result.error is not None

    def test_library_mode_fails_fast_without_retry(self):
        """Dict library IRs with invalid step types must fail-fast on attempt 1."""
        registry = load_default_registry()
        loop = ExecutionLoop(
            planner=Planner(registry=registry),
            runtime_adapter=PyFluentAdapter(runtime=MockRuntime()),
            validator=ValidatorWrapper(registry=registry),
            ir_mode="library",
            max_retries=5,  # Would allow retries in llm mode, but not library
        )

        # Inject an invalid dict IR into the library
        original = ir_library._LIBRARY.copy()
        ir_library._LIBRARY["_bad_test"] = {
            "steps": [{"type": "not_a_real_step"}]
        }
        try:
            result = loop.run(ir_name="_bad_test")
            assert not result.success
            assert result.attempts == 1  # fail-fast: exactly 1 attempt
        finally:
            ir_library._LIBRARY.clear()
            ir_library._LIBRARY.update(original)

    def test_workflow_ir_does_not_fail_fast_on_advisory_issues(self, loop):
        """Workflow IRs with non-registry params proceed past validation."""
        # simple_distribution uses non-registry liquid_class / tip_type values,
        # so semantic validation will flag issues — but execution should still succeed.
        result = loop.run(ir_name="simple_distribution")
        assert result.success  # advisory issues never block execution

    def test_result_contains_plans_and_log(self, loop):
        result = loop.run(ir_name="simple_distribution_dict")
        assert len(result.plans) > 0
        assert len(result.execution_log) > 0

    def test_result_contains_state(self, loop):
        result = loop.run(ir_name="simple_distribution_dict")
        assert result.state is not None

    def test_result_contains_validation_feedback(self, loop):
        result = loop.run(ir_name="simple_distribution_dict")
        assert result.validation_feedback is not None
        assert result.validation_feedback.is_valid

    def test_workflow_result_contains_plans_and_log(self, loop):
        result = loop.run(ir_name="distribution_mix_incubate")
        assert len(result.plans) > 0
        assert len(result.execution_log) > 0

    def test_workflow_result_contains_state(self, loop):
        result = loop.run(ir_name="distribution_mix_incubate")
        assert result.state is not None
