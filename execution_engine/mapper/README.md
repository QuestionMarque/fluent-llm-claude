# mapper/

Direct 1:1 translation from a validated `Step` to a `RuntimeCall` — the
concrete `(method_name, variables)` pair that the runtime adapter
executes.

This package replaces the former `planner/` package. The registry
guarantees that every step type is supported by exactly one method, so no
candidate selection or scoring is ever needed. Once validation passes,
mapping is purely mechanical.

---

## Algorithm

```
Step
  │
  ▼
StepMapper.map(step)
  ├── registry.methods_supporting(step.type)   → exactly one Method
  └── VariableMapper.map(step)                 → runtime variable dict
  │
  ▼
RuntimeCall { method_name, variables, step_id }
```

The lookup is trivial. The only real work is in `VariableMapper`, which
normalizes parameter aliases and drops `None` values so the strict runtime
adapter does not have to.

---

## Modules

### `step_mapper.py`
`StepMapper` — the public entry point.

- `StepMapper(registry).map(step) → RuntimeCall`
- `StepMapper(registry).map_workflow(workflow) → List[RuntimeCall]`

Raises `MapperError` if zero or more than one methods are registered for
a step type. Both conditions indicate a registry bug and should never
happen for validated input — validation already rejects unknown step
types, and `test_mapper.TestRegistryInvariant` enforces the 1:1
invariant across the whole registry.

### `variable_mapper.py`
`VariableMapper` — step-type-aware translation of `step.params` into the
runtime variable dict.

| Step family | Mapped variables |
|-------------|------------------|
| `reagent_distribution`, `sample_transfer` | volumes, tip_type, liquid_class, labware_source/target, wells, replicates |
| `aspirate_volume`, `dispense_volume`, `mix_volume` | volumes, labware, liquid_class, well_offsets, cycles |
| `transfer_labware` | labware_name, target_location, target_position |
| `get_tips` | tip_type (normalized), airgap_volume, airgap_speed |
| `drop_tips_to_location` | labware |
| `empty_tips` | labware_empty_tips, labware, liquid_class |

Alias normalization: `DiTi_type` / `diti_type` → `tip_type`,
`well_offset` → `well_offsets`. `None` values are never included — the
runtime adapter rejects them in strict mode.

---

## Why there's no planning

The capability registry (`registry.yaml`) defines exactly one method per
step type:

| Step type | Method |
|-----------|--------|
| `reagent_distribution` | `ReagentDistribution` |
| `sample_transfer` | `SampleTransfer` |
| `aspirate_volume` | `AspirateVolume` |
| `dispense_volume` | `DispenseVolume` |
| `mix_volume` | `MixVolume` |
| `transfer_labware` | `TransferLabware` |
| `get_tips` | `GetTips` |
| `drop_tips_to_location` | `DropTipsToLocation` |
| `empty_tips` | `EmptyTips` |

Because the step type uniquely identifies the method, there is never a
choice to make. The validation layer has already confirmed that tips,
liquid classes, volumes, and labware satisfy the registry constraints
for that method. Nothing is left to decide.

If a future step type needs multiple implementations (e.g. `reagent_distribution`
via FCA vs. MCA96), reintroduce a planning layer at that point — but do not
add one prophylactically now.

---

## Minimal Usage

```python
from execution_engine.capability_registry.loader import load_default_registry
from execution_engine.mapper.step_mapper import StepMapper
from execution_engine.models.workflow import Step

registry = load_default_registry()
mapper = StepMapper(registry=registry)

step = Step(type="reagent_distribution", params={
    "volumes": [100],
    "labware_source": "Reagent_Trough_100mL",
    "labware_target": "Plate_96_Well",
    "tip_type": "DiTi_200uL",
    "liquid_class": "Buffer",
})

call = mapper.map(step)
print(call.method_name)  # "ReagentDistribution"
print(call.variables)    # {"volumes": [100], "tip_type": "DiTi_200uL", ...}
```
