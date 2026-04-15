# models/

Defines the core shared data contracts for the entire execution engine.
All packages import from here — nothing depends on `models/` in return.

---

## Modules

### `workflow.py`
Defines `Step`, `Workflow`, and `STEP_SCHEMA`.

**`STEP_SCHEMA`** is the single authoritative contract for step structure:
```python
STEP_SCHEMA = {
    "reagent_distribution": {
        "required": ["volumes", "labware_source", "labware_target"],
        "optional": ["tip_type", "DiTi_type", "diti_type", "liquid_class", ...]
    },
    ...
}
```
Validation reads required fields **only** from this schema. No other module
should duplicate required-field logic.

**`Step`** — a single executable workflow step:
```python
@dataclass
class Step:
    type: str               # must match a STEP_SCHEMA key
    params: Dict[str, Any]  # all step-specific arguments
    id: Optional[str]       # for logging and traceability
```

**`Workflow`** — an ordered list of steps with optional metadata:
```python
@dataclass
class Workflow:
    steps: List[Step]
    metadata: Dict[str, Any]
```

### `runtime_call.py`
Defines `RuntimeCall` and the `from_step` classmethod that builds one
from a validated `Step`.

```python
@dataclass
class RuntimeCall:
    method_name: str          # FluentControl method to invoke
    variables: Dict[str, Any] # runtime variable key-value pairs
    step_id: Optional[str]    # mirrors originating Step.id

    @classmethod
    def from_step(cls, step, registry) -> "RuntimeCall": ...
```

Because every step type maps to exactly one method (enforced by
`RegistryValidator` at load time), `from_step` is a 1:1 lookup —
no selection or scoring. The same module also holds the variable-
translation helpers (`_map_distribution`, `_map_liquid_operation`, ...)
that:

- normalize aliases (`DiTi_type` / `diti_type` → `tip_type`,
  `well_offset` → `well_offsets`)
- filter out IR fields that are not runtime variables
- drop `None` values (the runtime adapter is strict)

Raises `ValueError` if the step type is not supported by any registered
method — defensive guard for callers that bypass validation.

### `state.py`
Defines `State` — lightweight mutable execution state.

```python
@dataclass
class State:
    tip_loaded: bool
    well_volumes: Dict[str, float]   # well_id -> current µL
    execution_history: List[dict]
```

Mutated by `workflow/state_manager.py` after each step.

### `feedback.py`
Defines `FeedbackItem` and `ValidationFeedback` — the output contract
from the validation layer.

```python
@dataclass
class FeedbackItem:
    type: str         # machine-readable category
    message: str      # human-readable description
    suggestion: str   # corrective action hint
    context: str      # step id or field name
    severity: str     # "error" | "warning"

@dataclass
class ValidationFeedback:
    errors: List[FeedbackItem]
    warnings: List[FeedbackItem]
    retry_prompt: Optional[str]

    @property
    def is_valid(self) -> bool: ...
```

---

## Role in the Architecture

```
STEP_SCHEMA   ──► validation/             (schema checks)
              ──► capability_registry/    (load-time coverage check)
Step/Workflow ──► workflow/               (decomposition)
              ──► validation/             (input to validator)
              ──► RuntimeCall.from_step   (constructed into a runtime call)
RuntimeCall   ──► runtime/                (method + variables to execute)
State         ──► orchestration/          (state tracking)
Feedback      ──► orchestration/          (retry loop decisions)
```

Models are **pure data** — no business logic, no side effects.
Every other package depends on models; models depend on nothing.

---

## Minimal Usage

```python
from execution_engine.models import Step, Workflow, STEP_SCHEMA

step = Step(
    type="reagent_distribution",
    params={
        "volumes": [100],
        "labware_source": "Reagent_Trough_100mL",
        "labware_target": "Plate_96_Well",
        "tip_type": "DiTi_200uL",
        "liquid_class": "Buffer",
    },
    id="distribute_0",
)

workflow = Workflow(steps=[step])

# Check schema contract
schema = STEP_SCHEMA["reagent_distribution"]
print(schema["required"])  # ['volumes', 'labware_source', 'labware_target']
```
