# planner/

Decision-making layer. Takes a validated `Step` and returns the best `Plan`
for executing it via the runtime adapter.

---

## Algorithm

The planner runs a strict three-stage pipeline:

```
Step
  │
  ▼
CandidateSelector.select(step)
  → filters by: step type support, tip type, volume range, liquid/tip compatibility
  → returns: List[Method]  (hard failures eliminated)
  │
  ▼
ScoringEngine.score(step, method)   ← for each candidate
  → scores on: coverage, tip, volume, liquid, efficiency, risk
  → returns: (score: float, reasoning: str)
  │
  ▼
best candidate selected (highest score)
  │
  ▼
VariableMapper.map(step, method_name)
  → translates step params to runtime variable dict
  → normalizes aliases (DiTi_type → tip_type, well_offset → well_offsets)
  → omits None values (runtime is strict)
  │
  ▼
Plan { method_name, variables, score, reasoning, step_id }
```

---

## Modules

### `candidate_selector.py`
**Hard filter only.** No scoring happens here.

A method passes if:
1. Its `supports` list contains `step.type`
2. If `tip_type` is specified → must be in `method.tip_types`
3. If `volumes` are specified → max volume must fit `[min_volume_uL, max_volume_uL]`
4. If both `tip_type` and `liquid_class` are specified → must be compatible per registry

### `scoring.py`
**Soft ranking only.** No filtering happens here.

Weighted scoring across 6 dimensions (weights sum to 1.0):

| Dimension  | Weight | Meaning |
|-----------|--------|---------|
| coverage  | 0.25   | method supports the step type |
| tip       | 0.20   | tip matched (neutral if unspecified) |
| volume    | 0.20   | volume in range, centered = higher |
| liquid    | 0.15   | liquid class matched (neutral if unspecified) |
| efficiency| 0.10   | specialized methods preferred over general |
| risk      | 0.10   | penalty for tip/liquid incompatibility |

Score is in `[0.0, 1.0]`. Reasoning is a semicolon-separated trace string.

### `variable_mapper.py`
**Step-type-aware mapping.** Each step family has its own mapping logic:

| Step family | Mapped variables |
|-------------|-----------------|
| `reagent_distribution`, `sample_transfer` | volumes, tip_type, liquid_class, labware_source/target, wells |
| `aspirate_volume`, `dispense_volume`, `mix_volume` | volumes, labware, liquid_class, well_offsets, cycles |
| `transfer_labware` | labware_name, target_location, target_position |
| `get_tips` | tip_type (normalized) |
| `drop_tips_to_location` | labware |
| `empty_tips` | labware_empty_tips |
| `incubate` | duration_seconds, temperature_celsius, device |

Alias normalization: `DiTi_type` / `diti_type` → `tip_type`,
`well_offset` → `well_offsets`. None values are never included.

### `planner.py`
Orchestrates the three stages. `Planner.plan(step)` returns a `Plan`.
`Planner.plan_workflow(steps)` plans an entire workflow in order.

Raises `PlannerError` when no candidate is found (indicates registry gap
or invalid step parameters that slipped past validation).

---

## Minimal Usage

```python
from execution_engine.capability_registry.loader import load_default_registry
from execution_engine.models.workflow import Step
from execution_engine.planner.planner import Planner

registry = load_default_registry()
planner = Planner(registry=registry, enable_liquid_inference=True)

step = Step(type="reagent_distribution", params={
    "volumes": [100],
    "labware_source": "Reagent_Trough_100mL",
    "labware_target": "Plate_96_Well",
    "tip_type": "DiTi_200uL",
    "liquid_class": "Buffer",
})

plan = planner.plan(step)
print(plan.method_name)  # "ReagentDistribution"
print(plan.score)        # e.g. 0.9519
print(plan.variables)    # {"volumes": [100], "tip_type": "DiTi_200uL", ...}
print(plan.reasoning)    # "coverage=yes; tip='DiTi_200uL' matched; ..."
```
