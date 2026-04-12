# execution_engine/

Python SDK for AI-driven lab automation on the Tecan Fluent liquid handler.

Converts a natural-language IFU (Instruction for Use) or a predefined TDF
(Test Definition Format) into validated, planned, and executable runtime calls
through a PyFluent-style adapter.

---

## Architecture

```
IFU text  ──or──  TDF library name
        │
        ▼
   [ llm/ ]  (optional — skipped in library mode)
   LLMClient.generate_tdf(prompt)
        │
        ▼
   [ workflow/ ]
   WorkflowDecomposer.decompose(tdf)  →  Workflow
        │
        ▼
   [ validation/ ]
   ValidatorWrapper.validate_workflow(workflow)  →  ValidationFeedback
        │
        ├── invalid + llm mode  →  build retry prompt, loop back
        └── invalid + library   →  fail fast
        │
        ▼  (valid)
   for each step:
   [ planner/ ]
   Planner.plan(step)  →  Plan { method_name, variables, score }
        │
        ▼
   [ runtime/ ]
   PyFluentAdapter.execute(method_name, variables)  →  ExecutionResult
        │
        ▼
   [ workflow/ ]
   StateManager.update(step, success)  →  mutate State
        │
        ▼
   ExecutionLoopResult { success, plans, execution_log, state, ... }
```

All decisions are grounded in `capability_registry/` — no hardcoded
method/tip/liquid knowledge anywhere in the planning or validation layers.

---

## Package Summary

| Package | Role |
|---------|------|
| `models/` | Core data contracts (Step, Workflow, Plan, State, Feedback) |
| `capability_registry/` | Registry of methods, tips, liquid classes, labware |
| `validation/` | Schema + semantic validation; LLM retry prompt builder |
| `planner/` | CandidateSelector → ScoringEngine → VariableMapper |
| `runtime/` | PyFluentAdapter; strict variable validation; hardware bridge |
| `workflow/` | TDF → Workflow decomposer; StateManager; DependencyResolver hook |
| `orchestration/` | ExecutionLoop; TDF library; library/LLM mode control |
| `llm/` | LLMClient; PromptBuilder; schema (optional) |
| `utils/` | Structured logger |

---

## Execution Modes

**Library mode** (`tdf_mode="library"`)
- Deterministic: same TDF name → same workflow every time
- Fail-fast: validation errors are code bugs, not runtime conditions
- No network access required

**LLM mode** (`tdf_mode="llm"`)
- Dynamic: IFU text → LLM → TDF → workflow
- Self-correcting: validation errors produce a retry prompt
- Requires `OPENAI_API_KEY`

---

## Quick Start

```python
from execution_engine.capability_registry.loader import load_default_registry
from execution_engine.validation.validator_wrapper import ValidatorWrapper
from execution_engine.planner.planner import Planner
from execution_engine.runtime.pyfluent_adapter import PyFluentAdapter
from execution_engine.orchestration.execution_loop import ExecutionLoop

registry = load_default_registry()

loop = ExecutionLoop(
    planner=Planner(registry=registry),
    runtime_adapter=PyFluentAdapter(runtime=your_fluent_runtime),
    validator=ValidatorWrapper(registry=registry),
    tdf_mode="library",
)

result = loop.run(tdf_name="distribution_mix_incubate")
print(result.success)
```

See `main.py` at the project root for a full runnable demo with a stub runtime.

---

## Extension Points

The system is designed for clean extension without modifying existing code:

| Feature | Where to add |
|---------|-------------|
| New step type | `STEP_SCHEMA` in `models/workflow.py` + method in `registry.yaml` |
| Custom step decomposer | `@register_decomposer` in `workflow/decomposer.py` |
| New LLM provider | `LLMClient._call_provider()` in `llm/llm_client.py` |
| Dependency-based ordering | `workflow/dependency_resolver.py` |
| New scoring dimension | `planner/scoring.py` WEIGHTS dict |
| Richer state tracking | `models/state.py` + `workflow/state_manager.py` |
| Multi-instrument support | New adapter alongside `runtime/pyfluent_adapter.py` |
