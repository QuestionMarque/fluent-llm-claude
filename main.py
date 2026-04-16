"""main.py — Library-mode demo of the fluent-llm execution engine.

Runs the full preparation pipeline (obtain IR → decompose → validate →
build RuntimeCalls) and emits the portable JSON artifact that a PyFluent
executor would consume.

PyFluent execution itself is intentionally NOT included here — this demo
only produces and inspects the artifact. To actually run the workflow
on a Fluent (or FluentVisionX simulation), see the notes at the bottom
of this file.
"""
import json
import os

from dotenv import load_dotenv

load_dotenv()

from execution_engine.capability_registry.loader import load_default_registry
from execution_engine.validation.validator_wrapper import ValidatorWrapper
from execution_engine.orchestration.execution_loop import (
    ExecutionLoop,
    runtime_calls_to_dict_list,
)
from execution_engine.workflow.decomposer import WorkflowDecomposer


def main() -> int:
    print("=" * 62)
    print("  fluent-llm Execution Engine — Library Mode Demo")
    print("  (validation + RuntimeCall JSON artifact; no execution)")
    print("=" * 62)

    # 1. Load capability registry (fail-fast on load-time invariants)
    registry = load_default_registry()
    print(
        f"\n[Setup] Registry loaded: "
        f"{len(registry.methods)} methods, "
        f"{len(registry.tips)} tip types, "
        f"{len(registry.liquid_classes)} liquid classes, "
        f"{len(registry.labware)} labware types"
    )

    # 2. Build the loop without a runtime adapter — preparation doesn't
    #    need one. Leaving runtime_adapter=None will cause loop.run() to
    #    raise, but we only call loop.prepare() here, which is backend-free.
    validator = ValidatorWrapper(registry=registry)
    decomposer = WorkflowDecomposer()

    loop = ExecutionLoop(
        registry=registry,
        validator=validator,
        decomposer=decomposer,
        runtime_adapter=None,
        ir_mode="library",
        max_retries=1,
    )

    # 3. Run the preparation phase for one of the bundled IR examples
    ir_name = "pipetting_cycle"
    print(f"\n[Run] Preparing IR: '{ir_name}'")
    prepared = loop.prepare(ir_name=ir_name)

    # 4. Validation summary
    print("\n" + "=" * 62)
    print(f"  Result:   {'READY TO EXECUTE' if prepared.success else 'PREPARATION FAILED'}")
    print(f"  Attempts: {prepared.attempts}")

    if prepared.error:
        print(f"  Error:    {prepared.error}")

    if prepared.workflow:
        print(f"\n  Workflow steps: {len(prepared.workflow.steps)}")

    if prepared.validation_feedback:
        fb = prepared.validation_feedback
        print(f"\n  Validation: {len(fb.errors)} error(s), {len(fb.warnings)} warning(s)")
        for e in fb.errors:
            print(f"    [ERROR] {e.message}")
        for w in fb.warnings:
            print(f"    [WARN]  {w.message}")

    if not prepared.success:
        print("\n" + "=" * 62)
        return 1

    # 5. Emit the portable JSON artifact — the input to any backend that
    #    will execute the workflow (PyFluent, direct VisionX, a queue, ...).
    calls_json = runtime_calls_to_dict_list(prepared.runtime_calls)

    print(f"\n  Runtime calls ({len(calls_json)}):")
    for entry in calls_json:
        print(f"    [{entry['step_id']}] → {entry['method_name']}")
        for k, v in entry["variables"].items():
            print(f"        {k}: {v!r}")

    print("\n  --- Portable JSON artifact (feed this to the executor) ---")
    print(json.dumps(calls_json, indent=2, default=str))

    # 6. Optionally persist it alongside the demo run.
    out_path = os.path.join(os.path.dirname(__file__), f"{ir_name}.runtime_calls.json")
    with open(out_path, "w") as f:
        json.dump(calls_json, f, indent=2, default=str)
    print(f"\n  Wrote artifact to: {out_path}")

    # 7. Note on how to execute (deliberately not wired up here).
    print(
        "\n  To execute this artifact on a Fluent, plug in a PyFluent\n"
        "  backend (or its simulation mode):\n\n"
        "    from pyfluent.backends.fluent_visionx import FluentVisionX\n"
        "    from execution_engine.runtime.pyfluent_adapter import PyFluentAdapter\n"
        "    backend = FluentVisionX(simulation_mode=True)\n"
        "    async with PyFluentAdapter(backend) as adapter:\n"
        "        results = await adapter.execute_workflow(prepared.runtime_calls)\n"
    )

    print("=" * 62)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
