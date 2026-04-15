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
- **RuntimeCall** — the `(method_name, variables)` pair a validated Step is
  mapped to. Produced by `StepMapper`; consumed by the runtime adapter.

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
   [ mapper/ ]       StepMapper.map(step)                 →  RuntimeCall
        │                (1:1 lookup — no scoring, no selection)
        ▼
   [ runtime/ ]      PyFluentAdapter.execute(method_name, variables)
        │
        ▼
   [ workflow/ ]     StateManager.update(step, success)  →  State
```

All lookups are grounded in `capability_registry/data/registry.yaml`.
No hardcoded method/tip/liquid knowledge anywhere else.

Because the registry guarantees exactly one method per step type, the
mapping stage is purely mechanical — there is no planner, no candidate
selection, and no scoring. Validation is the last decision point; once
it passes, the workflow can be executed directly.

---

## Execution modes

- **`ir_mode="library"`** — loads IR from `orchestration/IR_examples/<name>.json`; fail-fast on validation errors; deterministic.
- **`ir_mode="llm"`** — generates IR via LLM; retries with corrective prompt up to `max_retries`.

---

## IR source: `IR_examples/` (JSON files)

`execution_engine/orchestration/IR_examples/` holds one JSON file per
predefined workflow. `ExecutionLoop._obtain_ir` loads
`IR_examples/<ir_name>.json` in library mode. Each file is a Dict IR that
goes through the full pipeline: decompose → schema + semantic validation →
plan → execute. Because library IRs are authored, validation failure is
treated as a code bug (fail-fast, no retries).

Available examples (as of this writing): `pipetting_cycle`, `just_tips`,
`transfer_samples_plate_to_plate`, `transfer_samples_tubes_to_plate`,
`dilute_samples_from_tube`, `dilute_samples_from_full_plate`,
`serial_dilution`, `sample_tube_to_plate_replicates`, `fill_plate_hotel`,
`distribute_antisera`, `distribute_antigens`, `add_tRBC`.

> Note: `ExecutionLoop.run` still contains a branch for pre-built
> `Workflow` instances (advisory-only semantic validation, no fail-fast).
> That branch is dormant for library mode now that IR is loaded from JSON
> (always a dict), but it remains reachable for callers that pass a
> `Workflow` directly via the LLM path or tests.

---

## Package layout

| Package | Role |
|---------|------|
| `models/` | `Step`, `Workflow`, `RuntimeCall`, `State`, `ValidationFeedback`; `STEP_SCHEMA` |
| `capability_registry/` | `registry.yaml` loader; typed frozen dataclasses |
| `validation/` | Schema + semantic validation; LLM retry prompt builder |
| `mapper/` | `StepMapper` (1:1 step→method lookup) + `VariableMapper` |
| `runtime/` | `PyFluentAdapter`; strict variable validation |
| `workflow/` | `WorkflowDecomposer`; `StateManager`; `DependencyResolver` hook |
| `orchestration/` | `ExecutionLoop`; `IR_examples/` (JSON IRs) |
| `llm/` | `LLMClient`; `PromptBuilder`; `IR_SCHEMA` |

---

## Key files

- `execution_engine/models/workflow.py` — `STEP_SCHEMA` (single source of truth for step structure)
- `execution_engine/capability_registry/data/registry.yaml` — all methods, tips, liquid classes, labware, rules
- `execution_engine/orchestration/IR_examples/*.json` — all predefined IRs (one file per workflow)
- `execution_engine/orchestration/execution_loop.py` — `ExecutionLoop`; `ir_mode`/`ir_name` params
- `main.py` — runnable demo in library mode with stub runtime

---

## STEP_SCHEMA rules

- Single source of truth in `models/workflow.py`.
- Required fields enforced in schema validation layer only — never duplicated elsewhere.
- Tip type aliases recognized everywhere: `tip_type`, `DiTi_type`, `diti_type`.
- Step types currently defined: `reagent_distribution`, `sample_transfer`,
  `aspirate_volume`, `dispense_volume`, `mix_volume`, `transfer_labware`,
  `get_tips`, `drop_tips_to_location`, `empty_tips`.
- `mix` and `incubate` were removed — they are not compatible with Fluent
  Control. Use `mix_volume` for mixing.

---

## Mapping rules

- `StepMapper` looks up the one method that supports a step type via
  `registry.methods_supporting(step.type)`. The 1:1 invariant
  (exactly one method per step type) is enforced at registry load
  time by `RegistryValidator` — `load_registry()` raises
  `RegistryLoadError` if any step type has zero or multiple supporting
  methods, so the mapper trusts the result unconditionally.
- `VariableMapper` translates `step.params` into the runtime variable dict:
  - normalizes aliases (`DiTi_type` / `diti_type` → `tip_type`,
    `well_offset` → `well_offsets`)
  - drops `None` values (runtime adapter is strict)
  - handles per-step-family field sets (distribution vs liquid op vs
    labware transfer vs tip ops)

If a future step type ever needs multiple implementations, reintroduce
a planning/selection layer at that point — not prophylactically.

---

## Registry load-time validation

`capability_registry/loader.load_registry()` runs
`RegistryValidator` immediately and refuses to return a broken
registry. Errors (raise `RegistryLoadError`):

- a step type claimed by more than one method (ambiguous)
- a step type in `STEP_SCHEMA` with no supporting method (missing coverage)

Warnings (returned via `RegistryValidator().validate(registry)`,
not raised): methods/compatibility matrix referencing unknown tips or
liquid classes.

This collapses what would otherwise be N per-step `MapperError`
failures into one clear startup failure.

---

## Test suite

```
tests/unit/
  test_models.py
  test_validation.py
  test_mapper.py
  test_capability_registry.py
  test_runtime.py
  test_orchestration.py
```

Run with: `python3 -m pytest tests/ -q`
Current count: 83 tests, all passing.

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
