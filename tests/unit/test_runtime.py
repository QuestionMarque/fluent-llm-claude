import pytest
from execution_engine.runtime.pyfluent_adapter import (
    PyFluentAdapter, RuntimeAdapterError, ExecutionResult,
)


class MockRuntime:
    """Simulated FluentRuntime for testing."""
    def __init__(self):
        self.calls = []

    def PrepareMethod(self, method_name: str):
        self.calls.append(("PrepareMethod", method_name))

    def SetVariableValue(self, name: str, value):
        self.calls.append(("SetVariableValue", name, value))

    def RunMethod(self) -> str:
        self.calls.append(("RunMethod",))
        return "OK"


class MockMethodManager:
    def run_method(self, method_name: str, variables: dict) -> str:
        return f"executed:{method_name}"


class TestPyFluentAdapter:
    def test_raises_without_runtime_or_method_manager(self):
        with pytest.raises(RuntimeAdapterError):
            PyFluentAdapter()

    def test_execute_via_runtime_succeeds(self):
        runtime = MockRuntime()
        adapter = PyFluentAdapter(runtime=runtime)
        result = adapter.execute("TestMethod", {"param": "value"})
        assert result.success
        assert result.method_name == "TestMethod"

    def test_runtime_called_in_correct_order(self):
        runtime = MockRuntime()
        adapter = PyFluentAdapter(runtime=runtime)
        adapter.execute("TestMethod", {"k": "v"})
        assert runtime.calls[0] == ("PrepareMethod", "TestMethod")
        assert runtime.calls[1] == ("SetVariableValue", "k", "v")
        assert runtime.calls[2] == ("RunMethod",)

    def test_execute_via_method_manager(self):
        mm = MockMethodManager()
        adapter = PyFluentAdapter(method_manager=mm)
        result = adapter.execute("MyMethod", {"x": 1})
        assert result.success
        assert result.raw_result == "executed:MyMethod"

    def test_strict_mode_rejects_none_value(self):
        runtime = MockRuntime()
        adapter = PyFluentAdapter(runtime=runtime, strict=True)
        result = adapter.execute("TestMethod", {"key": None})
        assert not result.success
        assert "None" in result.error

    def test_non_strict_allows_none_value(self):
        runtime = MockRuntime()
        adapter = PyFluentAdapter(runtime=runtime, strict=False)
        result = adapter.execute("TestMethod", {"key": None})
        assert result.success

    def test_rejects_non_dict_variables(self):
        runtime = MockRuntime()
        adapter = PyFluentAdapter(runtime=runtime)
        result = adapter.execute("TestMethod", [("k", "v")])
        assert not result.success
        assert "dict" in result.error

    def test_rejects_non_string_key(self):
        runtime = MockRuntime()
        adapter = PyFluentAdapter(runtime=runtime)
        result = adapter.execute("TestMethod", {123: "value"})
        assert not result.success

    def test_empty_variables_succeeds(self):
        runtime = MockRuntime()
        adapter = PyFluentAdapter(runtime=runtime)
        result = adapter.execute("NoVarMethod", {})
        assert result.success

    def test_execution_result_contains_variables(self):
        runtime = MockRuntime()
        adapter = PyFluentAdapter(runtime=runtime)
        variables = {"tip_type": "DiTi_200uL", "volumes": [100]}
        result = adapter.execute("SomeMethod", variables)
        assert result.variables == variables
