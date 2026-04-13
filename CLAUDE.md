# CLAUDE.md — fluent-llm-claude project context

## What this project is

Python SDK for AI-driven lab automation on the Tecan Fluent liquid handler.
Converts a natural-language IFU (Instruction for Use) or a predefined IR
(Intermediate Representation) into validated, planned, and executable runtime
calls through a PyFluent-style adapter.

GitHub repo: https://github.com/QuestionMarque/fluent-llm-claude (branch: main)

---

## Key terminology

- **IR (Intermediate Representation)** — the internal format describing a workflow
  as an ordered list of typed steps with parameters. Formerly called TDF (Test
  Definition Format); the rename was done in full across the codebase.
- **IFU (Instruction for Use)** — natural-language lab protocol; input for LLM mode.
- **Step** — a single typed operation (e.g. `reagent_distribution`, `get_tips`).
- **Workflow** — an ordered list of Steps.
- **Plan** — output of the Planner for one Step: method name + runtime variables + score.

---

## Architecture overview

```
IFU text  ──or──  IR library name
        │
        ▼
   [ llm/ ]          LLMClient.generate_ir(prompt)         (LLM mode only)
        │
        ▼
   [ workflow/ ]     WorkflowDecomposer.decompose(ir)  →  Workflow
        │
        ▼
   [ validation/ ]   ValidatorWrapper.validate_workflow()  →  ValidationFeedback
        │
        ▼
   [ planner/ ]      CandidateSelector → ScoringEngine → VariableMapper  →  Plan
        │
        ▼
   [ runtime/ ]      PyFluentAdapter.execute(method_name, variables)
        │
        ▼
   [ workflow/ ]     StateManager.update(step, success)  →  State
```

All decisions are grounded in `capability_registry/data/registry.yaml`.
No hardcoded method/tip/liquid knowledge anywhere else.

---

## Execution modes

- **`ir_mode="library"`** — loads IR from `ir_library`; fail-fast on validation errors; deterministic.
- **`ir_mode="llm"`** — generates IR via LLM; retries with corrective prompt up to `max_retries`.

---

## Two IR formats in the library

`execution_engine/orchestration/ir_library.py` holds two kinds of entries:

| Format | Keys | Execution path |
|--------|------|----------------|
| Dict IR | `*_dict` names (e.g. `simple_distribution_dict`) | decompose → full schema+semantic validation → fail-fast in library mode |
| Workflow IR | all others (e.g. `simple_distribution`) | skip decomposition; advisory-only semantic validation; never fail-fast |

`get_ir(name)` returns `Union[Dict, Workflow]`. The execution loop checks
`isinstance(result, Workflow)` to pick the path.

---

## Package layout

| Package | Role |
|---------|------|
| `models/` | `Step`, `Workflow`, `Plan`, `State`, `ValidationFeedback`; `STEP_SCHEMA` |
| `capability_registry/` | `registry.yaml` loader; typed frozen dataclasses |
| `validation/` | Schema + semantic validation; LLM retry prompt builder |
| `planner/` | `CandidateSelector` → `ScoringEngine` → `VariableMapper` |
| `runtime/` | `PyFluentAdapter`; strict variable validation |
| `workflow/` | `WorkflowDecomposer`; `StateManager`; `DependencyResolver` hook |
| `orchestration/` | `ExecutionLoop`; `ir_library` |
| `llm/` | `LLMClient`; `PromptBuilder`; `IR_SCHEMA` |

---

## Key files

- `execution_engine/models/workflow.py` — `STEP_SCHEMA` (single source of truth for step structure)
- `execution_engine/capability_registry/data/registry.yaml` — all methods, tips, liquid classes, labware, rules
- `execution_engine/orchestration/ir_library.py` — all predefined IRs
- `execution_engine/orchestration/execution_loop.py` — `ExecutionLoop`; `ir_mode`/`ir_name` params
- `main.py` — runnable demo in library mode with stub runtime

---

## STEP_SCHEMA rules

- Single source of truth in `models/workflow.py`.
- Required fields enforced in schema validation layer only — never duplicated elsewhere.
- Tip type aliases recognized everywhere: `tip_type`, `DiTi_type`, `diti_type`.
- `mix` step type is an alias for `mix_volume` with extended field names (`volume_uL`, `target`).

---

## CandidateSelector (planner) behavior

- Hard-filters methods by supported step type.
- Volume range check always applies.
- Tip-type and liquid/tip compatibility checks **only apply when the value is a known registry entry**.
  Unknown values (device-specific aliases like `FCA_DiTi_200uL`) pass through without rejection.

---

## Test suite

```
tests/unit/
  test_models.py
  test_validation.py
  test_planner.py
  test_runtime.py
  test_orchestration.py
```

Run with: `python3 -m pytest tests/ -q`
Current count: 95 tests, all passing.

---

## Commands

```bash
python3 -m pytest tests/ -q          # run all tests
python3 main.py                       # run library-mode demo
git push origin main                  # push to GitHub
```

---

## Conventions

- Python 3; no type: ignore; dataclasses throughout.
- `_set_if(target, key, value)` — only write to dict if value is not None (runtime strictness).
- Registry is the authority — never hardcode tip/liquid/method knowledge in code.
- Extension without modification: new step types go in `STEP_SCHEMA` + `registry.yaml`; new decomposers use `@register_decomposer`.
