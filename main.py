"""main.py — End-to-end demonstration of the fluent-llm execution engine.

Runs in library mode by default (no LLM or network access required).
To use LLM mode: set OPENAI_API_KEY in a .env file and switch ir_mode="llm".
"""
import os
from dotenv import load_dotenv

load_dotenv()

from execution_engine.capability_registry.loader import load_default_registry
from execution_engine.validation.validator_wrapper import ValidatorWrapper
from execution_engine.mapper.step_mapper import StepMapper
from execution_engine.runtime.pyfluent_adapter import PyFluentAdapter
from execution_engine.orchestration.execution_loop import ExecutionLoop
from execution_engine.workflow.decomposer import WorkflowDecomposer


# ---------------------------------------------------------------------------
# Stub FluentRuntime — replace with real PyFluent bindings in production
# ---------------------------------------------------------------------------
class FluentRuntime:
    """Simulated Fluent hardware runtime for demonstration purposes."""

    def PrepareMethod(self, method_name: str) -> None:
        print(f"    [FluentRuntime] PrepareMethod({method_name!r})")

    def SetVariableValue(self, name: str, value) -> None:
        print(f"    [FluentRuntime] SetVariableValue({name!r}, {value!r})")

    def RunMethod(self) -> str:
        print(f"    [FluentRuntime] RunMethod() → OK")
        return "OK"


# ---------------------------------------------------------------------------
# Demo state manager (optional — illustrates how state could be observed)
# ---------------------------------------------------------------------------
class DemoStateManager:
    def __init__(self):
        self.step_count = 0

    def on_step_complete(self, step_id: str, success: bool):
        self.step_count += 1
        status = "✓" if success else "✗"
        print(f"    [StateManager] {status} step #{self.step_count}: {step_id}")


def main():
    print("=" * 62)
    print("  fluent-llm Execution Engine — Library Mode Demo")
    print("=" * 62)

    # 1. Load capability registry
    registry = load_default_registry()
    print(
        f"\n[Setup] Registry loaded: "
        f"{len(registry.methods)} methods, "
        f"{len(registry.tips)} tip types, "
        f"{len(registry.liquid_classes)} liquid classes, "
        f"{len(registry.labware)} labware types"
    )

    # 2. Instantiate components
    validator = ValidatorWrapper(registry=registry)
    mapper = StepMapper(registry=registry)
    fluent_runtime = FluentRuntime()
    adapter = PyFluentAdapter(runtime=fluent_runtime, strict=True)
    decomposer = WorkflowDecomposer()

    # 3. Configure execution loop in library mode
    loop = ExecutionLoop(
        mapper=mapper,
        runtime_adapter=adapter,
        validator=validator,
        decomposer=decomposer,
        ir_mode="library",
        max_retries=1,
        # llm_client=LLMClient(provider="openai", model="gpt-4o-mini")  # enable for LLM mode
    )

    # 4. Run a predefined IR from the library
    ir_name = "pipetting_cycle"
    print(f"\n[Run] Executing IR: '{ir_name}'")
    result = loop.run(ir_name=ir_name)

    # 5. Display results
    print("\n" + "=" * 62)
    print(f"  Result:   {'SUCCESS' if result.success else 'FAILED'}")
    print(f"  Attempts: {result.attempts}")

    if result.error:
        print(f"  Error:    {result.error}")

    if result.workflow:
        print(f"\n  Workflow steps: {len(result.workflow.steps)}")

    print(f"\n  Runtime calls ({len(result.runtime_calls)}):")
    for call in result.runtime_calls:
        print(f"    [{call.step_id}] → {call.method_name}")
        for k, v in call.variables.items():
            print(f"        {k}: {v!r}")

    if result.state:
        print(f"\n  Final State:")
        print(f"    tip_loaded:   {result.state.tip_loaded}")
        print(f"    well_volumes: {result.state.well_volumes}")

    print(f"\n  Execution Log:")
    for entry in result.execution_log:
        ok = entry.get("execution_success", False)
        status = "OK  " if ok else "FAIL"
        err = f" | {entry['error']}" if entry.get("error") else ""
        print(f"    [{status}] {entry['step_id']} → {entry.get('method_name', 'N/A')}{err}")

    if result.validation_feedback:
        fb = result.validation_feedback
        print(f"\n  Validation: {len(fb.errors)} error(s), {len(fb.warnings)} warning(s)")
        for e in fb.errors:
            print(f"    [ERROR] {e.message}")
        for w in fb.warnings:
            print(f"    [WARN] {w.message}")

    print("\n" + "=" * 62)
    return 0 if result.success else 1


if __name__ == "__main__":
    raise SystemExit(main())
