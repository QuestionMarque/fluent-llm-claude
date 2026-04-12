# validation/

Safety and correctness layer. Sits between workflow decomposition and planning.
No invalid input ever reaches the planner or runtime.

---

## Modules

### `validator_wrapper.py`
`ValidatorWrapper` — the main entry point for all validation.

Validation is split into two distinct layers:

**Layer 1 — Schema validation** (`validate_workflow`):
Structural checks driven by `STEP_SCHEMA`. Detects:
- Unknown step types
- Missing required fields (reads required list **only** from `STEP_SCHEMA`)

**Layer 2 — Semantic validation** (`validate_step`):
Registry-grounded checks. Detects:
- Unknown tip types
- Unknown liquid classes
- Tip volume out of range
- Liquid/tip incompatibility
- Unspecified tip type or liquid class (warnings)
- Unknown labware (warnings)

**Why two layers?**
Schema errors are structural — they indicate a malformed TDF.
Semantic errors require registry knowledge — they indicate a physically
invalid or risky operation. Separating them keeps each layer testable
in isolation and makes the error taxonomy clear.

**Alias support:**
All three aliases for tip type are recognized everywhere:
`tip_type`, `DiTi_type`, `diti_type`

**Labware field support:**
`labware`, `labware_source`, `labware_target`, `labware_empty_tips`,
`labware_name`, `source`, `target`

### `feedback_builder.py`
`FeedbackBuilder` — converts `ValidationFeedback` into:
- A short human-readable summary (`summarize`)
- A structured LLM retry prompt (`build_retry_prompt`)

`ERROR_TAXONOMY` maps each error type to a label and corrective guidance,
making retry prompts specific and actionable rather than generic.

---

## Feedback Loop

```
validate_workflow(workflow)
    → ValidationFeedback { errors, warnings, is_valid }

if not is_valid and llm_mode:
    FeedbackBuilder.build_retry_prompt(feedback, original_prompt)
    → retry_prompt (sent back to LLM)

if not is_valid and library_mode:
    → fail fast (code bug, not a runtime condition)
```

---

## Minimal Usage

```python
from execution_engine.capability_registry.loader import load_default_registry
from execution_engine.models.workflow import Step, Workflow
from execution_engine.validation.validator_wrapper import ValidatorWrapper
from execution_engine.validation.feedback_builder import FeedbackBuilder

registry = load_default_registry()
validator = ValidatorWrapper(registry=registry)

step = Step(type="reagent_distribution", params={
    "volumes": [100],
    "labware_source": "Reagent_Trough_100mL",
    "labware_target": "Plate_96_Well",
    "tip_type": "DiTi_200uL",
    "liquid_class": "Buffer",
})

feedback = validator.validate_workflow(Workflow(steps=[step]))
print(feedback.is_valid)   # True or False
print(feedback.errors)     # List[FeedbackItem]
print(feedback.warnings)   # List[FeedbackItem]

if not feedback.is_valid:
    builder = FeedbackBuilder()
    print(builder.summarize(feedback))
    print(builder.build_retry_prompt(feedback, original_prompt="..."))
```
