"""demo_llm.py — Showcase the LLM → validated IR feedback loop.

Runs the *LLM* path of the execution engine end-to-end without requiring
an API key or network access. Uses `DemoBackend` with a scripted
sequence that deliberately produces a flawed IR on the first turn so
you can see the validation feedback loop in action:

    Turn 1  LLM returns an IR missing required fields
            → validation fails
            → feedback is sent back to the LLM as the next user turn
    Turn 2  LLM returns a corrected IR
            → validation passes
            → workflow is decomposed and RuntimeCalls are built
    Output  Portable JSON artifact (same format main.py emits)

To run against a real OpenAI model instead:

    export LLM_PROVIDER=openai
    export LLM_MODEL=gpt-4o-mini
    export OPENAI_API_KEY=sk-...
    python demo_llm.py --provider env

By default the script forces provider=demo so it never touches the network.
"""
from __future__ import annotations

import argparse
import json
import os
import sys

from dotenv import load_dotenv

load_dotenv()

from execution_engine.capability_registry.loader import load_default_registry
from execution_engine.llm import (
    DemoBackend,
    IRGenerator,
    LLMClient,
    PromptBuilder,
)
from execution_engine.orchestration.execution_loop import (
    ExecutionLoop,
    runtime_calls_to_dict_list,
)
from execution_engine.validation.validator_wrapper import ValidatorWrapper
from execution_engine.workflow.decomposer import WorkflowDecomposer


SAMPLE_IFU = (
    "Distribute 100 µL of Buffer from the Reagent_Trough_100mL "
    "into all 96 wells of the Plate_96_Well target plate using "
    "DiTi_200uL tips. Drop tips into the waste when done."
)

# A two-response script for the demo backend.
# First response: deliberately incomplete — missing required fields
#                 that semantic validation will flag.
# Second response: a full, registry-grounded IR that passes validation.
FLAWED_FIRST_IR = {
    "name": "distribute_buffer",
    "assumptions": [
        "Target plate already loaded",
    ],
    "steps": [
        {
            "id": "step_0",
            "type": "reagent_distribution",
            # Intentionally incomplete: most required fields missing.
            "params": {
                "volumes": [100],
                "liquid_class": "Buffer",
            },
        },
    ],
}

CORRECTED_IR = {
    "name": "distribute_buffer",
    "assumptions": [
        "Target plate already loaded",
        "Reagent trough is pre-filled with Buffer",
    ],
    "steps": [
        {
            "id": "step_0",
            "type": "reagent_distribution",
            "params": {
                "volumes": [100],
                "sample_count": 96,
                "DiTi_type": "DiTi_200uL",
                "DiTi_waste": "Waste_Container",
                "labware_source": "Reagent_Trough_100mL",
                "labware_target": "Plate_96_Well",
                "liquid_class": "Buffer",
                "selected_wells_source": [1],
                "selected_wells_target": list(range(1, 97)),
                "labware_empty_tips": "Waste_Container",
            },
        },
        {
            "id": "step_1",
            "type": "drop_tips_to_location",
            "params": {"labware": "Waste_Container"},
        },
    ],
}


def build_ir_generator_demo(registry) -> IRGenerator:
    """Compose an IRGenerator wired to the scripted DemoBackend."""
    backend = DemoBackend(script=[FLAWED_FIRST_IR, CORRECTED_IR])
    client = LLMClient(backend=backend, max_json_retries=1)
    prompt_builder = PromptBuilder(registry=registry)
    validator = ValidatorWrapper(registry=registry)
    return IRGenerator(
        client=client,
        prompt_builder=prompt_builder,
        validator=validator,
        max_retries=2,
    )


def build_ir_generator_env(registry) -> IRGenerator:
    """Compose an IRGenerator using the provider chosen by env vars."""
    client = LLMClient.from_env()
    prompt_builder = PromptBuilder(registry=registry)
    validator = ValidatorWrapper(registry=registry)
    return IRGenerator(
        client=client,
        prompt_builder=prompt_builder,
        validator=validator,
        max_retries=3,
    )


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--provider",
        choices=("demo", "env"),
        default="demo",
        help=(
            "'demo' uses the scripted DemoBackend (default, no API key). "
            "'env' reads LLM_PROVIDER/LLM_MODEL/OPENAI_API_KEY."
        ),
    )
    parser.add_argument(
        "--ifu",
        default=SAMPLE_IFU,
        help="Natural-language IFU. Default is the built-in sample.",
    )
    args = parser.parse_args(argv)

    print("=" * 72)
    print("  fluent-llm — LLM Mode Demo (natural language → validated IR)")
    print(f"  Provider: {args.provider}")
    print("=" * 72)

    registry = load_default_registry()
    print(f"\n[Setup] Registry: {len(registry.methods)} methods, "
          f"{len(registry.tips)} tips, "
          f"{len(registry.liquid_classes)} liquid classes.")

    if args.provider == "env":
        generator = build_ir_generator_env(registry)
    else:
        generator = build_ir_generator_demo(registry)

    print(f"\n[IFU]\n{args.ifu}\n")

    loop = ExecutionLoop(
        registry=registry,
        validator=ValidatorWrapper(registry=registry),
        decomposer=WorkflowDecomposer(),
        ir_generator=generator,
        runtime_adapter=None,
        ir_mode="llm",
        max_retries=2,
    )

    prepared = loop.prepare(prompt=args.ifu)

    print("\n" + "=" * 72)
    print(f"  Result:   {'READY TO EXECUTE' if prepared.success else 'FAILED'}")
    print(f"  Attempts: {prepared.attempts}")

    if prepared.validation_feedback:
        fb = prepared.validation_feedback
        print(f"  Validation: {len(fb.errors)} error(s), {len(fb.warnings)} warning(s)")
        for e in fb.errors:
            print(f"    [ERROR] {e.message}")
        for w in fb.warnings:
            print(f"    [WARN]  {w.message}")

    if prepared.error:
        print(f"  Error:    {prepared.error}")

    if not prepared.success:
        return 1

    print(f"\n  Workflow steps: {len(prepared.workflow.steps)}")
    print(f"  Runtime calls:  {len(prepared.runtime_calls)}")

    calls_json = runtime_calls_to_dict_list(prepared.runtime_calls)

    print("\n  --- Portable JSON artifact (same format as main.py) ---")
    print(json.dumps(calls_json, indent=2, default=str))

    out_path = os.path.join(os.path.dirname(__file__), "llm_demo.runtime_calls.json")
    with open(out_path, "w") as f:
        json.dump(calls_json, f, indent=2, default=str)
    print(f"\n  Wrote artifact to: {out_path}")

    print("\n" + "=" * 72)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
