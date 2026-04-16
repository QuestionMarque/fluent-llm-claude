"""PyFluent adapter — async bridge from RuntimeCall to a FluentVisionX-compatible backend.

The adapter is deliberately thin:
- It takes a *backend* (any object with the PyFluent FluentVisionX API shape:
  setup/stop + per-operation async methods + run_method / wait_for_channel).
- It translates one `RuntimeCall` into one awaited backend call, either via
  the dispatch table (dedicated PyFluent method) or via the generic
  `backend.run_method(...)` fallback for FluentControl methods that PyFluent
  hasn't surfaced as Python APIs yet.
- It enforces the same strict "no None values" rule at the boundary.

Usage:

    async with PyFluentAdapter(backend) as adapter:
        result = await adapter.execute(call)

    # or on a prepared workflow:
    results = await adapter.execute_workflow(calls)
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, TYPE_CHECKING

from ..models.runtime_call import RuntimeCall

if TYPE_CHECKING:
    # Backend is duck-typed to the FluentVisionX shape. We avoid importing
    # PyFluent at module import time so validation, mapping, and JSON export
    # remain usable without the runtime dependency installed.
    pass


class RuntimeAdapterError(Exception):
    pass


@dataclass
class ExecutionResult:
    """Structured result from executing a single RuntimeCall."""
    success: bool
    method_name: str
    variables: Dict[str, Any] = field(default_factory=dict)
    step_id: Optional[str] = None
    raw_result: Optional[Any] = None
    error: Optional[str] = None


# Dispatch table: FluentControl method name -> PyFluent backend attribute.
# When a registered method has a dedicated async method on the backend we
# invoke it directly with **variables. Missing entries fall through to the
# generic run_method path.
DISPATCH: Dict[str, str] = {
    "AspirateVolume": "aspirate_volume",
    "DispenseVolume": "dispense_volume",
    "GetTips": "get_tips",
    "DropTipsToLocation": "drop_tips_to_location",
    # The remaining FluentControl methods (ReagentDistribution,
    # SampleTransfer, MixVolume, TransferLabware, EmptyTips) don't have
    # dedicated PyFluent methods yet — they go via run_method.
}


class PyFluentAdapter:
    """Execution bridge between RuntimeCall and a FluentVisionX-compatible backend.

    Async-first. For synchronous callers (scripts, legacy tests) there are
    `execute_sync` and `execute_workflow_sync` convenience wrappers.

    The adapter is also an async context manager that owns the backend's
    setup/stop lifecycle:

        async with PyFluentAdapter(backend) as adapter:
            await adapter.execute_workflow(calls)
    """

    def __init__(
        self,
        backend: Any,
        strict: bool = True,
        channel_timeout: float = 90.0,
    ):
        if backend is None:
            raise RuntimeAdapterError(
                "PyFluentAdapter requires a backend "
                "(e.g. pyfluent.backends.fluent_visionx.FluentVisionX)."
            )
        self.backend = backend
        self.strict = strict
        self.channel_timeout = channel_timeout

    # --- Lifecycle -----------------------------------------------------

    async def setup(self) -> None:
        setup = getattr(self.backend, "setup", None)
        if setup is not None:
            await _maybe_await(setup())

    async def stop(self) -> None:
        stop = getattr(self.backend, "stop", None)
        if stop is not None:
            await _maybe_await(stop())

    async def __aenter__(self) -> "PyFluentAdapter":
        await self.setup()
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        await self.stop()

    # --- Execution -----------------------------------------------------

    async def execute(self, call: RuntimeCall) -> ExecutionResult:
        """Execute a single RuntimeCall against the backend."""
        try:
            self._validate_variables(call)
        except RuntimeAdapterError as e:
            return ExecutionResult(
                success=False,
                method_name=call.method_name,
                variables=call.variables,
                step_id=call.step_id,
                error=str(e),
            )

        try:
            dispatch_attr = DISPATCH.get(call.method_name)
            if dispatch_attr is not None and hasattr(self.backend, dispatch_attr):
                raw = await _maybe_await(
                    getattr(self.backend, dispatch_attr)(**call.variables)
                )
            else:
                raw = await self._execute_via_run_method(call)
        except Exception as e:
            return ExecutionResult(
                success=False,
                method_name=call.method_name,
                variables=call.variables,
                step_id=call.step_id,
                error=f"Backend raised: {e}",
            )

        return ExecutionResult(
            success=True,
            method_name=call.method_name,
            variables=call.variables,
            step_id=call.step_id,
            raw_result=raw,
        )

    async def execute_workflow(self, calls: List[RuntimeCall]) -> List[ExecutionResult]:
        """Execute each RuntimeCall sequentially. Stops nothing on failure —
        every call gets its own ExecutionResult; upstream decides what to do."""
        results: List[ExecutionResult] = []
        for call in calls:
            results.append(await self.execute(call))
        return results

    # --- Synchronous conveniences -------------------------------------

    def execute_sync(self, call: RuntimeCall) -> ExecutionResult:
        """Blocking wrapper around execute() — suitable for CLI demos and
        simple tests. Not for use from inside a running event loop."""
        return asyncio.run(self.execute(call))

    def execute_workflow_sync(self, calls: List[RuntimeCall]) -> List[ExecutionResult]:
        return asyncio.run(self.execute_workflow(calls))

    # --- Internals -----------------------------------------------------

    async def _execute_via_run_method(self, call: RuntimeCall) -> Any:
        """Generic path: start the FluentControl method on the API channel
        and wait for the channel to report completion."""
        run_method = getattr(self.backend, "run_method", None)
        if run_method is None:
            raise RuntimeAdapterError(
                f"Backend has no dedicated method for '{call.method_name}' "
                "and no run_method fallback."
            )
        raw = await _maybe_await(
            run_method(call.method_name, wait_for_completion=False, **call.variables)
        )
        wait_for_channel = getattr(self.backend, "wait_for_channel", None)
        if wait_for_channel is not None:
            await _maybe_await(wait_for_channel(timeout=self.channel_timeout))
        return raw

    def _validate_variables(self, call: RuntimeCall) -> None:
        if not isinstance(call.variables, dict):
            raise RuntimeAdapterError(
                f"Variables for '{call.method_name}' must be a dict, "
                f"got {type(call.variables).__name__}."
            )
        for key, value in call.variables.items():
            if not isinstance(key, str):
                raise RuntimeAdapterError(
                    f"Variable key {key!r} must be a string."
                )
            if self.strict and value is None:
                raise RuntimeAdapterError(
                    f"Variable '{key}' is None in strict mode. "
                    "Resolve or remove it before execution."
                )


async def _maybe_await(value: Any) -> Any:
    """Await `value` if it's a coroutine; otherwise return it as-is.

    PyFluent's surface is async, but tests and adapters may supply sync
    mocks. Accepting either keeps the adapter usable in both worlds.
    """
    if asyncio.iscoroutine(value):
        return await value
    return value
