# runtime/

Execution bridge between mapper output and the Fluent hardware runtime.
The only package that touches FluentControl — all other packages are
hardware-agnostic.

---

## Modules

### `pyfluent_adapter.py`
`PyFluentAdapter` — wraps the hardware runtime and enforces strict variable
validation before any call reaches the instrument.

---

## Two Execution Paths

### Path 1 — Runtime (low-level)
Maps directly to FluentControl scripting:

```
PrepareMethod(method_name)
SetVariableValue(name, value)   ← once per variable
...
RunMethod()
```

Use when you need fine-grained control or are working with FluentControl
in scripting mode. Pass a `runtime` object to the adapter.

### Path 2 — MethodManager (high-level)
Uses the PyFluent `method_manager` API:

```
method_manager.run_method(method_name, variables)
```

Use when integrating with a higher-level PyFluent session object.
Pass a `method_manager` object to the adapter.

At least one of the two must be provided — the adapter raises
`RuntimeAdapterError` at construction time if both are absent.

---

## Strict Variable Validation

Before any execution path is invoked, variables are validated:

1. `variables` must be a `dict`
2. All keys must be `str`
3. In strict mode (default `True`): no `None` values allowed

Failures return a failed `ExecutionResult` — the adapter never raises
exceptions into the caller for runtime errors.

```python
@dataclass
class ExecutionResult:
    success: bool
    method_name: str
    variables: Dict[str, Any]
    raw_result: Optional[Any]  # return value from RunMethod / run_method
    error: Optional[str]       # set on failure
```

Strict mode exists because `mapper.VariableMapper` guarantees no None
values in its output. If a None ever reaches the adapter, something
upstream went wrong — strict mode surfaces it immediately rather than
silently passing garbage to the instrument.

---

## Minimal Usage

```python
from execution_engine.runtime.pyfluent_adapter import PyFluentAdapter

# With a real FluentControl runtime object:
adapter = PyFluentAdapter(runtime=fluent_runtime, strict=True)

result = adapter.execute(
    method_name="ReagentDistribution",
    variables={
        "volumes": [100],
        "tip_type": "DiTi_200uL",
        "liquid_class": "Buffer",
        "labware_source": "Reagent_Trough_100mL",
        "labware_target": "Plate_96_Well",
    }
)

if result.success:
    print(f"Executed: {result.method_name}")
else:
    print(f"Failed: {result.error}")
```
