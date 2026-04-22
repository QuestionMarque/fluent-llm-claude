# Fluent-LLM

AI-driven lab-automation SDK for the Tecan Fluent liquid handler. Takes a
natural-language **Instruction for Use (IFU)** or a predefined
**Intermediate Representation (IR)** and produces validated, executable
runtime calls against a PyFluent-style backend.

- **Repo (Azure DevOps):** <https://alm.tecan.net/Utilities/MachineLearning/_git/Fluent-LLM>
- **Deep technical reference:** see [`CLAUDE.md`](./CLAUDE.md).

---

## Introduction

Fluent-LLM sits between a human-readable protocol and a physical
instrument. The pipeline is:

```
IFU text  ──or──  IR library name
      │
      ▼
 [ llm/ ]          IRGenerator.generate(ifu)  ◄──► LLMClient (OpenAI | Demo | …)
      │                    └─ multi-turn feedback loop with the validator
      ▼
 [ workflow/ ]     WorkflowDecomposer.decompose(ir)         →  Workflow
      │
      ▼
 [ validation/ ]   ValidatorWrapper.validate_workflow()     →  ValidationFeedback
      │
      ▼
 [ models/ ]       RuntimeCall.from_step(step, registry)    →  RuntimeCall
      │                    (1:1 lookup in capability_registry/registry.yaml)
      ▼
 [ runtime/ ]      PyFluentAdapter.execute(call)            (async, PyFluent)
      │
      ▼
 [ workflow/ ]     StateManager.update(step, success)       →  State
```

Everything non-mechanical is centralized: the capability registry
(`registry.yaml`) is the single source of truth for methods, tips,
liquid classes, labware, and compatibilities. The mapping from step
type to FluentControl method is 1:1 and enforced at registry load time,
so once a workflow validates it can be executed directly — no planning
or scoring layer.

There are two execution modes:

- **`library` mode** — deterministic. Loads a pre-authored IR JSON from
  `execution_engine/orchestration/IR_examples/`, validates fail-fast.
- **`llm` mode** — turns a natural-language IFU into an IR with an LLM.
  Validation errors are fed back to the same conversation as a new user
  turn, and the model is asked to revise. Supports OpenAI out of the
  box and a scripted Demo backend that needs no API key.

---

## Getting Started

### Prerequisites

- Python 3.10+
- pip

Optional (only needed for real hardware execution):
- [PyFluent](https://github.com/SLKS99/PyFluent) (liquid handler runtime)
- A Tecan Fluent with FluentControl API access, or its simulation mode
  via `FluentVisionX(simulation_mode=True)`.

### Installation

```bash
# 1. Clone
git clone https://alm.tecan.net/Utilities/MachineLearning/_git/Fluent-LLM
cd Fluent-LLM

# 2. Create a virtualenv (recommended)
python3 -m venv .venv
source .venv/bin/activate

# 3. Install the core dependencies
pip install -r requirements.txt

# 4. (optional) Install PyFluent for hardware execution
pip install "pyfluent @ git+https://github.com/SLKS99/PyFluent.git"
```

The core pipeline (validation, IR generation, JSON artifact emission)
runs without PyFluent installed. PyFluent is only imported when you
actually drive a Fluent backend.

### Environment setup

For LLM mode, put the provider configuration in a `.env` file at the
repo root (or export in your shell):

```ini
# .env — picked up automatically by main.py / demo_llm.py
LLM_PROVIDER=openai        # or "demo" for the scripted backend
LLM_MODEL=gpt-4o-mini
OPENAI_API_KEY=sk-...
```

All three are read by `LLMClient.from_env()`. The demo provider needs
no API key.

---

## Usage

### Library-mode demo (no LLM, no hardware)

```bash
python3 main.py
```

Loads the `pipetting_cycle` example from `IR_examples/`, validates it,
builds `RuntimeCall`s, prints the portable JSON artifact, and writes
it to `pipetting_cycle.runtime_calls.json`. Nothing is executed —
this is the input a runtime backend would consume.

### LLM-mode demo (no API key required)

```bash
python3 demo_llm.py
```

Runs the full IFU → validated IR flow with a scripted `DemoBackend`.
The first scripted response is deliberately flawed so you can see the
validation feedback loop kick in; the second is valid. Output:

```
[IRGenerator] Attempt 1
[IRGenerator] Validation: Invalid: 8 error(s), 1 warning(s).
[IRGenerator] Validation failed — sending feedback back to the LLM...

[IRGenerator] Attempt 2
[IRGenerator] Validation: Valid (0 warning(s)).
```

Run against a real OpenAI model instead:

```bash
python3 demo_llm.py --provider env
# with LLM_PROVIDER / LLM_MODEL / OPENAI_API_KEY set
```

Supply your own IFU:

```bash
python3 demo_llm.py --ifu "Transfer 50 µL from each sample tube to a 96-well plate."
```

### Minimal programmatic usage

Library mode, no hardware:

```python
from execution_engine.capability_registry.loader import load_default_registry
from execution_engine.validation.validator_wrapper import ValidatorWrapper
from execution_engine.orchestration.execution_loop import (
    ExecutionLoop, runtime_calls_to_dict_list,
)

registry = load_default_registry()
loop = ExecutionLoop(
    registry=registry,
    validator=ValidatorWrapper(registry=registry),
    ir_mode="library",
)
prepared = loop.prepare(ir_name="pipetting_cycle")
print(runtime_calls_to_dict_list(prepared.runtime_calls))
```

LLM mode, with the Demo backend:

```python
from execution_engine.llm import DemoBackend, IRGenerator, LLMClient, PromptBuilder
from execution_engine.validation.validator_wrapper import ValidatorWrapper

client = LLMClient(
    backend=DemoBackend(script=[YOUR_IR_DICT]),
    max_feedback_turns=5,   # hard safety cap on continue_with calls
)
gen = IRGenerator(
    client=client,
    prompt_builder=PromptBuilder(registry=registry),
    validator=ValidatorWrapper(registry=registry),
    max_retries=3,
)
result = gen.generate("Distribute 100 µL of Buffer into all 96 wells.")
if result.success:
    workflow = result.workflow        # ready to execute
    conv = result.conversation        # full chat transcript
```

### Executing on a Fluent (PyFluent)

Not wired up in `main.py` by default. One-liner once PyFluent is
installed:

```python
from pyfluent.backends.fluent_visionx import FluentVisionX
from execution_engine.runtime.pyfluent_adapter import PyFluentAdapter

backend = FluentVisionX(simulation_mode=True)
async with PyFluentAdapter(backend) as adapter:
    results = await adapter.execute_workflow(prepared.runtime_calls)
```

See the roadmap (and `CLAUDE.md`) for the planned `--execute` flag on
`main.py`.

---

## Tests

```bash
python3 -m pytest tests/ -q
```

Current count: **113 tests**, all passing.

```
tests/unit/
  test_models.py
  test_validation.py
  test_capability_registry.py
  test_runtime.py
  test_orchestration.py
  test_llm.py
```

---

## Project structure

```
Fluent-LLM/
├── main.py                         # Library-mode demo (validate + emit JSON)
├── demo_llm.py                     # LLM-mode demo (no API key)
├── requirements.txt
├── CLAUDE.md                       # Deep technical reference
├── tests/unit/                     # 113 unit tests
└── execution_engine/
    ├── models/                     # Step, Workflow, RuntimeCall (+ from_step), State, Feedback
    ├── capability_registry/        # registry.yaml + loader + load-time validator
    ├── validation/                 # Schema + semantic validator; feedback builder
    ├── workflow/                   # IR decomposer; StateManager; dependency hook
    ├── runtime/                    # Async PyFluent adapter
    ├── orchestration/              # ExecutionLoop (prepare / run / run_sync); IR_examples/
    └── llm/                        # LLMClient + backends (OpenAI, Demo); IRGenerator; PromptBuilder
```

Each package has a `README.md` with deeper documentation. See
[`CLAUDE.md`](./CLAUDE.md) for the full architecture, step schema,
mapping rules, and extension points.

---

## Key concepts

- **IR (Intermediate Representation)** — typed, ordered list of steps
  with parameters. JSON-serializable. What the LLM produces and what
  the library mode loads.
- **Step** — single typed operation (`reagent_distribution`, `get_tips`, …)
  matching a key in `STEP_SCHEMA`.
- **RuntimeCall** — `(method_name, variables, step_id)` ready for the
  runtime adapter. Built by `RuntimeCall.from_step(step, registry)`.
- **Capability registry** — YAML-defined source of truth. Every step
  type maps to exactly one method (enforced at load time).
- **Two execution modes** — `library` (authored IR, fail-fast) and
  `llm` (IFU → IR via LLM, multi-turn feedback loop).
- **Two retry budgets in LLM mode** — `max_json_retries` (JSON parse
  retries per call) and `max_feedback_turns` (hard cap on feedback
  loop turns per conversation; bounds token spend even against a
  non-converging model).

---

## Roadmap

Active TODO list with priority ordering lives in
[`CLAUDE.md`](./CLAUDE.md#roadmap--todo). Highlights:

- Install PyFluent as a real (uncommented) dependency and add an
  `--execute` flag to `main.py`.
- Round-trip the portable JSON artifact — `artifact/reader.py` and
  `artifact/writer.py` — so a saved run can be replayed without
  re-invoking the LLM.
- Embed a SHA256 hash of `registry.yaml` in the JSON artifact so
  replays fail loudly against a mismatched registry.
- PDF/docx IFU loader.
- Additional LLM backends (Anthropic, Azure OpenAI).
- Few-shot examples in `PromptBuilder`.

---

## Conventions

- Python 3; dataclasses throughout; no `type: ignore`.
- The registry is the authority — never hardcode method / tip / liquid
  knowledge in code.
- Extension without modification: add new step types in `STEP_SCHEMA`
  + `registry.yaml`; new decomposers via `@register_decomposer`; new
  LLM providers as new `LLMBackend` classes in `llm/backends.py`.
