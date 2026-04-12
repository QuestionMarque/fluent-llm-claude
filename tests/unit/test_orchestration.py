import pytest
from execution_engine.orchestration.execution_loop import ExecutionLoop, ExecutionLoopResult
from execution_engine.orchestration import tdf_library
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
        tdf_mode="library",
        max_retries=1,
    )


class TestTDFLibrary:
    def test_list_returns_non_empty(self):
        names = tdf_library.list_tdf_names()
        assert len(names) >= 3

    def test_all_expected_names_present(self):
        names = tdf_library.list_tdf_names()
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
            assert expected in names, f"Expected TDF '{expected}' not found in library"

    def test_dict_tdfs_present(self):
        names = tdf_library.list_tdf_names()
        for expected in (
            "simple_distribution_dict",
            "distribution_with_incubation_dict",
            "distribution_mix_incubate_dict",
        ):
            assert expected in names

    def test_get_dict_tdf_returns_dict_with_steps(self):
        tdf = tdf_library.get_tdf("simple_distribution_dict")
        assert isinstance(tdf, dict)
        assert "steps" in tdf
        assert len(tdf["steps"]) > 0

    def test_get_workflow_tdf_returns_workflow(self):
        tdf = tdf_library.get_tdf("simple_distribution")
        assert isinstance(tdf, Workflow)
        assert len(tdf.steps) > 0

    def test_get_unknown_tdf_raises_key_error(self):
        with pytest.raises(KeyError):
            tdf_library.get_tdf("this_does_not_exist")

    def test_all_library_tdfs_have_valid_step_types(self):
        for name in tdf_library.list_tdf_names():
            tdf = tdf_library.get_tdf(name)
            if isinstance(tdf, Workflow):
                for step in tdf.steps:
                    assert step.type in STEP_SCHEMA, (
                        f"TDF '{name}' step '{step.id}' has unknown type '{step.type}'"
                    )
            else:
                for step in tdf["steps"]:
                    assert step["type"] in STEP_SCHEMA, (
                        f"TDF '{name}' step '{step.get('id')}' has unknown type '{step['type']}'"
                    )

    def test_workflow_tdfs_have_non_empty_steps(self):
        workflow_names = [
            "simple_distribution", "distribution_mix_incubate",
            "serial_dilution", "distribute_antigens", "add_tRBC",
        ]
        for name in workflow_names:
            tdf = tdf_library.get_tdf(name)
            assert isinstance(tdf, Workflow)
            assert len(tdf.steps) > 0, f"'{name}' has no steps"

    def test_serial_dilution_has_many_steps(self):
        tdf = tdf_library.get_tdf("serial_dilution")
        assert isinstance(tdf, Workflow)
        # 1 get_tips + 10 * 4 (aspirate/dispense/mix/empty) + 1 aspirate + 1 drop = 43
        assert len(tdf.steps) > 10

    def test_distribute_antigens_has_dispense_steps(self):
        tdf = tdf_library.get_tdf("distribute_antigens")
        assert isinstance(tdf, Workflow)
        dispense_count = sum(1 for s in tdf.steps if s.type == "dispense_volume")
        assert dispense_count == 12  # one per column


class TestExecutionLoop:
    def test_simple_distribution_dict_succeeds(self, loop):
        result = loop.run(tdf_name="simple_distribution_dict")
        assert result.success
        assert result.attempts == 1

    def test_distribution_mix_incubate_dict_succeeds(self, loop):
        result = loop.run(tdf_name="distribution_mix_incubate_dict")
        assert result.success

    def test_distribution_with_incubation_dict_succeeds(self, loop):
        result = loop.run(tdf_name="distribution_with_incubation_dict")
        assert result.success

    def test_simple_distribution_workflow_succeeds(self, loop):
        result = loop.run(tdf_name="simple_distribution")
        assert result.success
        assert result.attempts == 1

    def test_distribution_mix_incubate_workflow_succeeds(self, loop):
        result = loop.run(tdf_name="distribution_mix_incubate")
        assert result.success

    def test_distribution_with_incubation_workflow_succeeds(self, loop):
        result = loop.run(tdf_name="distribution_with_incubation")
        assert result.success

    def test_just_tips_succeeds(self, loop):
        result = loop.run(tdf_name="just_tips")
        assert result.success

    def test_serial_dilution_succeeds(self, loop):
        result = loop.run(tdf_name="serial_dilution")
        assert result.success

    def test_distribute_antigens_succeeds(self, loop):
        result = loop.run(tdf_name="distribute_antigens")
        assert result.success

    def test_add_tRBC_succeeds(self, loop):
        result = loop.run(tdf_name="add_tRBC")
        assert result.success

    def test_unknown_tdf_name_returns_failure(self, loop):
        result = loop.run(tdf_name="nonexistent_workflow")
        assert not result.success
        assert result.error is not None

    def test_library_mode_fails_fast_without_retry(self):
        """Dict library TDFs with invalid step types must fail-fast on attempt 1."""
        registry = load_default_registry()
        loop = ExecutionLoop(
            planner=Planner(registry=registry),
            runtime_adapter=PyFluentAdapter(runtime=MockRuntime()),
            validator=ValidatorWrapper(registry=registry),
            tdf_mode="library",
            max_retries=5,  # Would allow retries in llm mode, but not library
        )

        # Inject an invalid dict TDF into the library
        original = tdf_library._LIBRARY.copy()
        tdf_library._LIBRARY["_bad_test"] = {
            "steps": [{"type": "not_a_real_step"}]
        }
        try:
            result = loop.run(tdf_name="_bad_test")
            assert not result.success
            assert result.attempts == 1  # fail-fast: exactly 1 attempt
        finally:
            tdf_library._LIBRARY.clear()
            tdf_library._LIBRARY.update(original)

    def test_workflow_tdf_does_not_fail_fast_on_advisory_issues(self, loop):
        """Workflow TDFs with non-registry params proceed past validation."""
        # simple_distribution uses non-registry liquid_class / tip_type values,
        # so semantic validation will flag issues — but execution should still succeed.
        result = loop.run(tdf_name="simple_distribution")
        assert result.success  # advisory issues never block execution

    def test_result_contains_plans_and_log(self, loop):
        result = loop.run(tdf_name="simple_distribution_dict")
        assert len(result.plans) > 0
        assert len(result.execution_log) > 0

    def test_result_contains_state(self, loop):
        result = loop.run(tdf_name="simple_distribution_dict")
        assert result.state is not None

    def test_result_contains_validation_feedback(self, loop):
        result = loop.run(tdf_name="simple_distribution_dict")
        assert result.validation_feedback is not None
        assert result.validation_feedback.is_valid

    def test_workflow_result_contains_plans_and_log(self, loop):
        result = loop.run(tdf_name="distribution_mix_incubate")
        assert len(result.plans) > 0
        assert len(result.execution_log) > 0

    def test_workflow_result_contains_state(self, loop):
        result = loop.run(tdf_name="distribution_mix_incubate")
        assert result.state is not None
