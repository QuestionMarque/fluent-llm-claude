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
  converted to. Produced by `RuntimeCall.from_step(step, registry)`;
  consumed by the runtime adapter.

---

## Architecture overview

```
IFU text  ──or──  IR library name
        │
        ▼
   [ llm/ ]          IRGenerator.generate(ifu) ────► LLMClient(backend)
        │                     └─ multi-turn feedback loop with validator
        │                        (backend = OpenAIBackend | DemoBackend | …)
        ▼
   [ workflow/ ]     WorkflowDecomposer.decompose(ir)  →  Workflow
        │
        ▼
   [ validation/ ]   ValidatorWrapper.validate_workflow()  →  ValidationFeedback
        │
        ▼
   [ models/ ]       RuntimeCall.from_step(step, registry) →  RuntimeCall
        │                (1:1 registry lookup + variable translation)
        ▼
   [ runtime/ ]      PyFluentAdapter.execute(call)            (async, PyFluent backend)
        │
        ▼
   [ workflow/ ]     StateManager.update(step, success)  →  State
```

All lookups are grounded in `capability_registry/data/registry.yaml`.
No hardcoded method/tip/liquid knowledge anywhere else.

Because the registry guarantees exactly one method per step type, the
step-to-call conversion is purely mechanical — no planner, no mapper
package, no candidate selection, no scoring. Validation is the last
decision point; once it passes, each step is converted to a
`RuntimeCall` directly and executed.

---

## Execution modes

- **`ir_mode="library"`** — loads IR from `orchestration/IR_examples/<name>.json`; fail-fast on validation errors; deterministic.
- **`ir_mode="llm"`** — delegates IR generation to an `IRGenerator` (LLM + validator + feedback loop). The feedback loop is a proper multi-turn chat: the model sees its own prior response plus structured validation errors, and revises. Requires `ir_generator=` on `ExecutionLoop`.

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
| `models/` | `Step`, `Workflow`, `RuntimeCall` (incl. `from_step` + variable mapping), `State`, `ValidationFeedback`; `STEP_SCHEMA` |
| `capability_registry/` | `registry.yaml` loader (with load-time validation); typed frozen dataclasses |
| `validation/` | Schema + semantic validation; LLM retry prompt builder |
| `runtime/` | `PyFluentAdapter`; strict variable validation |
| `workflow/` | `WorkflowDecomposer`; `StateManager`; `DependencyResolver` hook |
| `orchestration/` | `ExecutionLoop` (sync `prepare()` + async `run()`); `IR_examples/` (JSON IRs); `runtime_calls_to_dict_list` helper |
| `llm/` | `LLMClient` + `LLMBackend` (`OpenAIBackend`, `DemoBackend`); `IRGenerator` (multi-turn feedback loop); `PromptBuilder`; env-var factory |

---

## Key files

- `execution_engine/models/workflow.py` — `STEP_SCHEMA` (single source of truth for step structure)
- `execution_engine/capability_registry/data/registry.yaml` — all methods, tips, liquid classes, labware, rules
- `execution_engine/orchestration/IR_examples/*.json` — all predefined IRs (one file per workflow)
- `execution_engine/orchestration/execution_loop.py` — `ExecutionLoop`; `ir_mode`/`ir_name` params; `PreparedWorkflow`
- `execution_engine/llm/ir_generator.py` — IFU → validated IR feedback loop
- `execution_engine/llm/backends.py` — swappable provider backends (OpenAI, Demo, future)
- `execution_engine/runtime/pyfluent_adapter.py` — async bridge to PyFluent
- `main.py` — library-mode demo: validate + emit portable RuntimeCall JSON (no execution)
- `demo_llm.py` — LLM-mode demo: IFU → validated IR with scripted feedback loop (no API key)

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

## Step → RuntimeCall conversion

`RuntimeCall.from_step(step, registry)` (in `models/runtime_call.py`):

- Looks up the one method that supports `step.type` via
  `registry.methods_supporting(step.type)`. The 1:1 invariant is
  enforced at registry load time, so the lookup is unconditional.
- Translates `step.params` into the method's runtime variable dict:
  - normalizes aliases (`DiTi_type` / `diti_type` → `tip_type`,
    `well_offset` → `well_offsets`)
  - drops `None` values (runtime adapter is strict)
  - handles per-step-family field sets (distribution vs liquid op vs
    labware transfer vs tip ops)
- Raises `ValueError` if the step type is unknown — defensive guard
  for callers that bypass validation.

If a future step type ever needs multiple implementations, reintroduce
a selection layer at that point — not prophylactically.

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

This collapses what would otherwise be N per-step failures (and a
broken `RuntimeCall.from_step` invariant) into one clear startup
failure.

---

## LLM mode

- Backend abstraction in `llm/backends.py`: `LLMBackend` Protocol, with
  `OpenAIBackend` (requires `openai` + `OPENAI_API_KEY`) and
  `DemoBackend` (scripted responses — no network, no key).
- `LLMClient(backend=…, max_json_retries=…)` — provider-agnostic façade.
  `LLMClient.from_env()` reads `LLM_PROVIDER` (default `openai`),
  `LLM_MODEL` (default `gpt-4o-mini`), and `OPENAI_API_KEY`.
- `IRGenerator` owns the **multi-turn feedback loop**: sends the IFU,
  validates the returned IR, appends validation errors as a new user
  turn, asks the model to revise, loops up to `max_retries`.
- `ExecutionLoop` delegates LLM-mode preparation to `IRGenerator` —
  pass it via the `ir_generator=` constructor argument.
- `demo_llm.py` runs the full LLM scenario without an API key: a
  scripted `DemoBackend` deliberately returns a flawed IR first so the
  feedback loop is visible, then returns a valid IR.

---

## Test suite

```
tests/unit/
  test_models.py
  test_validation.py
  test_capability_registry.py
  test_runtime.py
  test_orchestration.py
  test_llm.py
```

Run with: `python3 -m pytest tests/ -q`
Current count: 107 tests, all passing.

---

## Commands

```bash
python3 -m pytest tests/ -q          # run all tests
python3 main.py                       # library-mode demo (validate + emit JSON)
python3 demo_llm.py                   # LLM-mode demo with DemoBackend (no API key)
python3 demo_llm.py --provider env    # same, but via LLM_PROVIDER / OPENAI_API_KEY
git push origin main                  # push to GitHub
```

---

## Conventions

- Python 3; no type: ignore; dataclasses throughout.
- `_set_if(target, key, value)` — only write to dict if value is not None (runtime strictness).
- Registry is the authority — never hardcode tip/liquid/method knowledge in code.
- Extension without modification: new step types go in `STEP_SCHEMA` + `registry.yaml`; new decomposers use `@register_decomposer`; new LLM providers are new `LLMBackend` classes in `llm/backends.py`.

---

## Roadmap / TODO

Running list of work the codebase has queued up. Keep it in priority order;
tick items off by moving them into a short "Recently done" section at the
bottom (or delete them once documented elsewhere).

### Near-term

- [ ] **Install PyFluent as a real dependency.** Today the line in
  `requirements.txt` is commented out. Once the upstream repo
  (`https://github.com/SLKS99/PyFluent`) is installable:
  `pip install "pyfluent @ git+https://github.com/SLKS99/PyFluent.git"`,
  un-comment the line, import `FluentVisionX` behind a try/except, and
  add a `--execute` flag to `main.py` that opens an async
  `PyFluentAdapter` against a `FluentVisionX(simulation_mode=True)`
  backend.
- [ ] **Round-trip the portable JSON artifact.** Add
  `execution_engine/artifact/{reader.py,writer.py}` so a saved
  `*.runtime_calls.json` can be loaded back into `List[RuntimeCall]`
  and handed to `PyFluentAdapter.execute_workflow`. Enables replay
  without re-running LLM / validation.
- [ ] **Registry hash in artifact metadata.** Embed a SHA256 of
  `registry.yaml` in the JSON artifact so a replay fails loudly if it
  runs against a different registry than it was generated with.

### LLM layer

- [ ] **Add a `pdf`/`docx` IFU loader.** `PromptBuilder.build(...)` is
  string-only today; a thin file-loader that extracts plain text would
  let real IFU documents drop in.
- [ ] **Anthropic backend + Azure OpenAI backend** in `llm/backends.py`.
  Each is roughly ~40 LOC once `OpenAIBackend` sets the pattern.
- [ ] **Few-shot examples in `PromptBuilder`.** Include one or two
  canonical IFU → IR pairs (picked from `IR_examples/`) so the LLM has
  worked-out examples alongside the schema/registry context.
- [ ] **Conversation transcript export.** `IRGenerationResult.conversation`
  is already available — add a helper to dump it to Markdown or JSONL
  for offline review.

### Testing / CI

- [ ] **`test_default_registry_has_no_warnings`.** The loader already
  catches errors; a test to assert zero warnings on the bundled
  `registry.yaml` would catch drift earlier.
- [ ] **Integration test: `demo_llm.py` runs to completion** (subprocess
  smoke test) so future refactors can't silently break the demo.

### Runtime / PyFluent bridge

- [ ] **Extend the `DISPATCH` table** in `pyfluent_adapter.py` as
  PyFluent surfaces more dedicated methods (`reagent_distribution`,
  `sample_transfer`, `mix_volume`, `transfer_labware`, `empty_tips`).
  Today those go via `run_method` fallback.
- [ ] **Optional `WorklistExporter`** that emits `.gwl`/`.csv` for
  workflows that are pure pipetting (no labware transfers, no generic
  `run_method` calls). Useful for offline audit/simulation.

### Recently done

- Replaced flat retry prompts with a proper multi-turn LLM feedback
  loop (`IRGenerator`).
- Introduced swappable `LLMBackend` (`OpenAIBackend`, `DemoBackend`)
  and `LLMClient.from_env()`.
- `demo_llm.py` runs the LLM scenario end-to-end with no API key.
- Async `PyFluentAdapter` + `ExecutionLoop.prepare`/`run`/`run_sync`
  split; portable `RuntimeCall` JSON artifact.
- Load-time registry invariant checking (`RegistryValidator` +
  `RegistryLoadError`).
- Deleted the mapper package; folded conversion into
  `RuntimeCall.from_step(step, registry)`.
