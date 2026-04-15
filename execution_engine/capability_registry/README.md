# capability_registry/

Single source of truth for what the Tecan Fluent system can do.
All validation and mapping lookups must be grounded here —
no hardcoded method/tip/liquid/labware knowledge anywhere else.

---

## Modules

### `models.py`
Frozen dataclasses for all registry entities:

| Class | Represents |
|-------|-----------|
| `Device` | Physical instrument on the worktable |
| `TipType` | A disposable tip with volume limits and filter flag |
| `LiquidClass` | Dispensing behavior profile |
| `Labware` | A plate, trough, rack, or waste container |
| `Method` | A FluentControl method with supported step types and variable list |
| `Rule` | A named constraint or preference rule |
| `ValidationIssue` / `ValidationResult` | Registry self-validation output |

All are `frozen=True` — registry entries are immutable after loading.

### `registry.py`
`CapabilityRegistry` — the central registry dataclass.

Key query methods:
```python
registry.get_tip(name)               → Optional[TipType]
registry.get_liquid_class(name)      → Optional[LiquidClass]
registry.get_labware(name)           → Optional[Labware]
registry.get_method(name)            → Optional[Method]
registry.methods_supporting(step_type) → List[Method]
registry.tip_compatible_with_liquid(tip, liquid) → bool
registry.infer_liquid_class_for_tip(tip) → Optional[str]
```

**Important:** `registry.methods` is a `dict`. Always iterate over
`.values()` — never treat `Method` objects as plain dicts.

### `loader.py`
`load_default_registry()` — loads the bundled `data/registry.yaml`.
`load_registry(path)` — loads from a custom YAML path.

Both run `RegistryValidator` immediately and raise `RegistryLoadError`
if any error-level issues are found. Pass `validate=False` to skip the
check (only useful in unit tests that intentionally build broken
registries). Warnings are not raised — fetch them with
`RegistryValidator().validate(registry)` directly if you need them.

### `validator.py`
`RegistryValidator` — checks the registry for internal consistency.

**Errors** (raised by the loader):
- a step type is supported by more than one method (ambiguous mapping)
- a step type in `STEP_SCHEMA` has no supporting method (incomplete coverage)

Both break the 1:1 step→method invariant that `RuntimeCall.from_step`
relies on, so the loader refuses the registry rather than letting the
problem surface later as a per-step failure.

**Warnings** (informational only):
- methods referencing tip types or liquid classes that don't exist
- compatibility matrix referencing unknown tips or liquid classes

Override the coverage check by passing
`validate(registry, expected_step_types=...)` — defaults to
`STEP_SCHEMA.keys()`.

### `data/registry.yaml`
The authoritative configuration file. Contains:
- **devices**: FCA, MCA96, MCA384, RGA, Te_Shake, Heated_Incubator, FRIDA_Reader
- **tips**: DiTi_10uL through DiTi_1000uL_Filter
- **liquid_classes**: Water, Serum, DMSO, Glycerol, Buffer
- **labware**: 96/384-well plates, troughs, tube racks, tip racks, waste
- **methods**: one per step type (ReagentDistribution, MixVolume, etc.)
- **tip_liquid_compatibility**: explicit compatibility matrix
- **rules**: named constraint/preference rules

---

## Architecture Note

The registry is **read-only at runtime**. Load it once at startup and
pass the same instance to `ValidatorWrapper`, `ExecutionLoop`, and any
caller of `RuntimeCall.from_step`. Never reload it per-step.

**Mapping invariant:** each step type must be supported by exactly one
method. `RegistryValidator` enforces this at load time — broken
registries cannot be returned to callers, so `RuntimeCall.from_step`
can do its 1:1 step→method lookup unconditionally.

---

## Minimal Usage

```python
from execution_engine.capability_registry.loader import load_default_registry

registry = load_default_registry()

# Query methods that can handle a step type
candidates = registry.methods_supporting("reagent_distribution")
for method in candidates:
    print(method.name, method.tip_types)

# Check tip/liquid compatibility
ok = registry.tip_compatible_with_liquid("DiTi_200uL", "Buffer")  # True
ok = registry.tip_compatible_with_liquid("DiTi_10uL", "Serum")   # False

# Look up a tip's volume range
tip = registry.get_tip("DiTi_200uL")
print(tip.min_volume_uL, tip.max_volume_uL)  # 2.0, 200.0
```
