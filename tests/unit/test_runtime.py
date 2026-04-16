"""Tests for the async PyFluentAdapter.

All async coroutines are driven with `asyncio.run()` to avoid pulling
in pytest-asyncio as a project dependency — these tests are short.
"""
import asyncio

import pytest

from execution_engine.models.runtime_call import RuntimeCall
from execution_engine.runtime.pyfluent_adapter import (
    ExecutionResult,
    PyFluentAdapter,
    RuntimeAdapterError,
)


class AsyncMockBackend:
    """Async mock backend matching the FluentVisionX surface used by the adapter."""

    def __init__(self):
        self.calls = []
        self.setup_called = False
        self.stop_called = False

    async def setup(self):
        self.setup_called = True

    async def stop(self):
        self.stop_called = True

    async def get_tips(self, **kwargs):
        self.calls.append(("get_tips", kwargs))
        return "tips_picked"

    async def aspirate_volume(self, **kwargs):
        self.calls.append(("aspirate_volume", kwargs))
        return "aspirated"

    async def dispense_volume(self, **kwargs):
        self.calls.append(("dispense_volume", kwargs))
        return "dispensed"

    async def drop_tips_to_location(self, **kwargs):
        self.calls.append(("drop_tips_to_location", kwargs))
        return "dropped"

    async def run_method(self, method_name, wait_for_completion=False, **kwargs):
        self.calls.append(("run_method", method_name, kwargs))
        return f"ran:{method_name}"

    async def wait_for_channel(self, timeout=90):
        self.calls.append(("wait_for_channel", timeout))


class SyncMockBackend:
    """Same shape but synchronous methods. The adapter should handle both."""

    def __init__(self):
        self.calls = []

    def setup(self):
        self.calls.append(("setup",))

    def stop(self):
        self.calls.append(("stop",))

    def aspirate_volume(self, **kwargs):
        self.calls.append(("aspirate_volume", kwargs))
        return "aspirated"

    def run_method(self, method_name, wait_for_completion=False, **kwargs):
        self.calls.append(("run_method", method_name, kwargs))
        return f"ran:{method_name}"

    def wait_for_channel(self, timeout=90):
        self.calls.append(("wait_for_channel", timeout))


def _run(coro):
    return asyncio.run(coro)


class TestPyFluentAdapterConstruction:
    def test_rejects_missing_backend(self):
        with pytest.raises(RuntimeAdapterError):
            PyFluentAdapter(backend=None)

    def test_async_context_manager_drives_setup_and_stop(self):
        backend = AsyncMockBackend()

        async def driver():
            async with PyFluentAdapter(backend):
                pass

        _run(driver())
        assert backend.setup_called
        assert backend.stop_called


class TestDispatchTable:
    def test_dedicated_method_is_called_directly(self):
        backend = AsyncMockBackend()
        adapter = PyFluentAdapter(backend)
        call = RuntimeCall(
            method_name="AspirateVolume",
            variables={"volumes": [50], "labware": "Plate_96_Well",
                       "liquid_class": "Water"},
            step_id="s1",
        )
        result = _run(adapter.execute(call))
        assert result.success
        assert result.step_id == "s1"
        assert result.raw_result == "aspirated"
        assert backend.calls[0][0] == "aspirate_volume"
        assert backend.calls[0][1]["volumes"] == [50]

    def test_get_tips_receives_diti_type_kwarg(self):
        backend = AsyncMockBackend()
        adapter = PyFluentAdapter(backend)
        call = RuntimeCall(
            method_name="GetTips",
            variables={"diti_type": "DiTi_200uL"},
        )
        result = _run(adapter.execute(call))
        assert result.success
        # Adapter passes variables straight through as kwargs.
        assert backend.calls[0] == ("get_tips", {"diti_type": "DiTi_200uL"})


class TestRunMethodFallback:
    def test_unmapped_method_goes_via_run_method(self):
        backend = AsyncMockBackend()
        adapter = PyFluentAdapter(backend, channel_timeout=30)
        call = RuntimeCall(
            method_name="ReagentDistribution",
            variables={"volumes": [100]},
        )
        result = _run(adapter.execute(call))
        assert result.success
        assert result.raw_result == "ran:ReagentDistribution"
        # run_method then wait_for_channel in that order.
        assert backend.calls[0][0] == "run_method"
        assert backend.calls[0][1] == "ReagentDistribution"
        assert backend.calls[1] == ("wait_for_channel", 30)


class TestSyncBackend:
    def test_adapter_handles_sync_backend_methods(self):
        backend = SyncMockBackend()
        adapter = PyFluentAdapter(backend)
        call = RuntimeCall(
            method_name="AspirateVolume",
            variables={"volumes": [50]},
        )
        result = _run(adapter.execute(call))
        assert result.success
        assert result.raw_result == "aspirated"


class TestStrictVariables:
    def test_none_value_rejected_in_strict_mode(self):
        backend = AsyncMockBackend()
        adapter = PyFluentAdapter(backend, strict=True)
        call = RuntimeCall(method_name="AspirateVolume", variables={"k": None})
        result = _run(adapter.execute(call))
        assert not result.success
        assert "None" in result.error

    def test_none_value_allowed_when_strict_off(self):
        backend = AsyncMockBackend()
        adapter = PyFluentAdapter(backend, strict=False)
        call = RuntimeCall(method_name="AspirateVolume", variables={"k": None})
        result = _run(adapter.execute(call))
        assert result.success

    def test_non_dict_variables_rejected(self):
        backend = AsyncMockBackend()
        adapter = PyFluentAdapter(backend)
        call = RuntimeCall(method_name="AspirateVolume", variables="not a dict")  # type: ignore[arg-type]
        result = _run(adapter.execute(call))
        assert not result.success
        assert "dict" in result.error


class TestBackendErrorsAreCaught:
    def test_backend_exception_becomes_failed_result(self):
        class BrokenBackend(AsyncMockBackend):
            async def aspirate_volume(self, **kwargs):
                raise RuntimeError("pump jammed")

        adapter = PyFluentAdapter(BrokenBackend())
        call = RuntimeCall(method_name="AspirateVolume", variables={})
        result = _run(adapter.execute(call))
        assert not result.success
        assert "pump jammed" in result.error


class TestExecuteWorkflow:
    def test_calls_are_executed_in_order(self):
        backend = AsyncMockBackend()
        adapter = PyFluentAdapter(backend)
        calls = [
            RuntimeCall(method_name="GetTips", variables={"diti_type": "DiTi_200uL"}),
            RuntimeCall(method_name="AspirateVolume", variables={"volumes": [50]}),
            RuntimeCall(method_name="DispenseVolume", variables={"volumes": [50]}),
            RuntimeCall(method_name="DropTipsToLocation", variables={"labware": "Waste"}),
        ]
        results = _run(adapter.execute_workflow(calls))
        assert [r.success for r in results] == [True, True, True, True]
        backend_method_names = [c[0] for c in backend.calls]
        assert backend_method_names == [
            "get_tips", "aspirate_volume", "dispense_volume", "drop_tips_to_location"
        ]


class TestSyncConvenience:
    def test_execute_sync_wraps_async(self):
        backend = AsyncMockBackend()
        adapter = PyFluentAdapter(backend)
        call = RuntimeCall(method_name="AspirateVolume", variables={"volumes": [5]})
        result = adapter.execute_sync(call)
        assert isinstance(result, ExecutionResult)
        assert result.success
