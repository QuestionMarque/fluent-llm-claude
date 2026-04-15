from dataclasses import dataclass, field
from typing import Any, Dict, Optional


class RuntimeAdapterError(Exception):
    pass


@dataclass
class ExecutionResult:
    """Structured result returned after executing a single method."""
    success: bool
    method_name: str
    variables: Dict[str, Any] = field(default_factory=dict)
    raw_result: Optional[Any] = None
    error: Optional[str] = None


class PyFluentAdapter:
    """Execution bridge between RuntimeCall variables and the Fluent hardware runtime.

    Two execution paths:
    1. method_manager path: calls method_manager.run_method(name, variables)
       — high-level PyFluent API, fewer control points
    2. runtime path: PrepareMethod → SetVariableValue × N → RunMethod
       — low-level control, matches FluentControl scripting model

    Strict mode (default on): rejects None variable values before execution.
    Disable only in tests or simulation scenarios.
    """

    def __init__(
        self,
        runtime=None,
        method_manager=None,
        strict: bool = True,
    ):
        if runtime is None and method_manager is None:
            raise RuntimeAdapterError(
                "PyFluentAdapter requires either 'runtime' or 'method_manager' to be set."
            )
        self.runtime = runtime
        self.method_manager = method_manager
        self.strict = strict

    def execute(self, method_name: str, variables: Dict[str, Any]) -> ExecutionResult:
        """Validate variables then execute the method via the available runtime path."""
        try:
            self._validate_variables(method_name, variables)
        except RuntimeAdapterError as e:
            return ExecutionResult(
                success=False,
                method_name=method_name,
                variables=variables,
                error=str(e),
            )

        try:
            if self.method_manager is not None:
                return self._execute_via_method_manager(method_name, variables)
            return self._execute_via_runtime(method_name, variables)
        except Exception as e:
            return ExecutionResult(
                success=False,
                method_name=method_name,
                variables=variables,
                error=f"Runtime exception: {e}",
            )

    def _validate_variables(self, method_name: str, variables: Any) -> None:
        if not isinstance(variables, dict):
            raise RuntimeAdapterError(
                f"Variables for '{method_name}' must be a dict, got {type(variables).__name__}."
            )
        for key, value in variables.items():
            if not isinstance(key, str):
                raise RuntimeAdapterError(
                    f"Variable key {key!r} must be a string."
                )
            if self.strict and value is None:
                raise RuntimeAdapterError(
                    f"Variable '{key}' is None in strict mode. "
                    "Resolve or remove it before execution."
                )

    def _execute_via_method_manager(
        self, method_name: str, variables: Dict[str, Any]
    ) -> ExecutionResult:
        result = self.method_manager.run_method(method_name, variables)
        return ExecutionResult(
            success=True,
            method_name=method_name,
            variables=variables,
            raw_result=result,
        )

    def _execute_via_runtime(
        self, method_name: str, variables: Dict[str, Any]
    ) -> ExecutionResult:
        self.runtime.PrepareMethod(method_name)
        for name, value in variables.items():
            self.runtime.SetVariableValue(name, value)
        result = self.runtime.RunMethod()
        return ExecutionResult(
            success=True,
            method_name=method_name,
            variables=variables,
            raw_result=result,
        )
