import pytest
from execution_engine.orchestration.execution_loop import ExecutionLoop, ExecutionLoopResult
from execution_engine.orchestration import tdf_library
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
        for expected in ("simple_distribution", "distribution_with_incubation", "distribution_mix_incubate"):
            assert expected in names

    def test_get_tdf_returns_steps(self):
        tdf = tdf_library.get_tdf("simple_distribution")
        assert "steps" in tdf
        assert len(tdf["steps"]) > 0

    def test_get_unknown_tdf_raises_key_error(self):
        with pytest.raises(KeyError):
            tdf_library.get_tdf("this_does_not_exist")

    def test_all_library_tdfs_have_valid_step_types(self):
        from execution_engine.models.workflow import STEP_SCHEMA
        for name in tdf_library.list_tdf_names():
            tdf = tdf_library.get_tdf(name)
            for step in tdf["steps"]:
                assert step["type"] in STEP_SCHEMA, (
                    f"TDF '{name}' step '{step.get('id')}' has unknown type '{step['type']}'"
                )


class TestExecutionLoop:
    def test_simple_distribution_succeeds(self, loop):
        result = loop.run(tdf_name="simple_distribution")
        assert result.success
        assert result.attempts == 1

    def test_distribution_mix_incubate_succeeds(self, loop):
        result = loop.run(tdf_name="distribution_mix_incubate")
        assert result.success

    def test_distribution_with_incubation_succeeds(self, loop):
        result = loop.run(tdf_name="distribution_with_incubation")
        assert result.success

    def test_unknown_tdf_name_returns_failure(self, loop):
        result = loop.run(tdf_name="nonexistent_workflow")
        assert not result.success
        assert result.error is not None

    def test_library_mode_fails_fast_without_retry(self):
        """Library mode must not retry — it fails on attempt 1."""
        registry = load_default_registry()
        loop = ExecutionLoop(
            planner=Planner(registry=registry),
            runtime_adapter=PyFluentAdapter(runtime=MockRuntime()),
            validator=ValidatorWrapper(registry=registry),
            tdf_mode="library",
            max_retries=5,  # Would allow retries in llm mode, but not library
        )

        # Inject an invalid TDF into the library
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

    def test_result_contains_plans_and_log(self, loop):
        result = loop.run(tdf_name="simple_distribution")
        assert len(result.plans) > 0
        assert len(result.execution_log) > 0

    def test_result_contains_state(self, loop):
        result = loop.run(tdf_name="simple_distribution")
        assert result.state is not None

    def test_result_contains_validation_feedback(self, loop):
        result = loop.run(tdf_name="simple_distribution")
        assert result.validation_feedback is not None
        assert result.validation_feedback.is_valid
