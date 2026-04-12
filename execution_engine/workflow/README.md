# workflow/

Translates dict IRs into typed `Workflow` objects and tracks execution state.

---

## Modules

### `decomposer.py`
`WorkflowDecomposer` — converts a dict IR into a `Workflow`.

Each IR step becomes a `Step(type, params, id)`. Step types that have
a registered decomposer function expand into multiple atomic steps.

**Extension hook — custom decomposers:**
```python
from execution_engine.workflow.decomposer import register_decomposer
from execution_engine.models.workflow import Step
from typing import List

@register_decomposer("serial_dilution")
def expand_serial_dilution(step: Step) -> List[Step]:
    # Return the atomic steps that make up a serial dilution
    return [...]
```
Step types without a registered decomposer pass through unchanged.
The core linear path is never affected.

### `state_manager.py`
`StateManager` — mutates `State` after each step completes.

Tracks:
- `tip_loaded`: updated on `get_tips` / `drop_tips_to_location` / `empty_tips`
- `well_volumes`: updated on dispense (`reagent_distribution`, `sample_transfer`,
  `dispense_volume`) and aspirate steps
- `execution_history`: log entry appended for every step

**Extension hook:** Add new fields to `State` and handle them in
`StateManager.update()` without altering any other module.

### `dependency_resolver.py`
`DependencyResolver` — placeholder for future DAG-based step ordering.

Currently a no-op (returns steps in declaration order). When loop/branch
support is needed:
1. Add `depends_on: List[str]` to `Step`
2. Implement topological sort in `DependencyResolver.resolve(workflow)`
3. Wire it into `WorkflowDecomposer` or `ExecutionLoop`

The rest of the system is unaffected.

---

## Current Architecture: Linear

```
dict IR
  ↓
WorkflowDecomposer.decompose(ir)
  ↓
Workflow(steps=[step_0, step_1, ...], metadata={...})
  ↓
ValidatorWrapper → Planner → Adapter (in order)
```

Future branching/loop support adds to this package —
it does not change the models or orchestration packages.

---

## Minimal Usage

```python
from execution_engine.workflow.decomposer import WorkflowDecomposer
from execution_engine.workflow.state_manager import StateManager

decomposer = WorkflowDecomposer()
ir = {
    "steps": [
        {"id": "step_0", "type": "get_tips", "tip_type": "DiTi_200uL"},
    ]
}

workflow = decomposer.decompose(ir)
print(workflow.steps[0].type)   # "get_tips"
print(workflow.steps[0].id)     # "step_0"

state_manager = StateManager()
state_manager.update(workflow.steps[0], success=True)
print(state_manager.get_state().tip_loaded)  # True
```
