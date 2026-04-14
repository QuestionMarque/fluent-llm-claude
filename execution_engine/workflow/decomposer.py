from typing import Callable, Dict, List

from ..models.workflow import Step, Workflow

# Extension hook: register custom decomposers for composite step types.
# Format: step_type -> callable(Step) -> List[Step]
# Example: @register_decomposer("serial_dilution") def ...(step): return [...]
STEP_DECOMPOSERS: Dict[str, Callable[[Step], List[Step]]] = {}


def register_decomposer(step_type: str):
    """Decorator to register a decomposer function for a composite step type.

    Use this when a step type should expand into multiple atomic steps.
    The core linear path is unaffected for step types without a decomposer.
    """
    def decorator(fn: Callable[[Step], List[Step]]):
        STEP_DECOMPOSERS[step_type] = fn
        return fn
    return decorator


class WorkflowDecomposer:
    """Translates a dict IR into a Workflow of atomic Steps.

    Currently operates linearly: each IR step maps to one or more Steps
    via the STEP_DECOMPOSERS registry. Step types without a decomposer
    pass through unchanged.

    Future loop/branch support: extend this class and add branching logic
    without altering the linear path for existing step types.
    """

    def decompose(self, ir: dict) -> Workflow:
        """Convert a dict IR into a Workflow."""
        raw_steps = ir.get("steps", [])
        steps: List[Step] = []

        for idx, raw in enumerate(raw_steps):
            step_type = raw.get("type", "unknown")
            if "params" in raw:
                params = raw["params"]
            else:
                params = {k: v for k, v in raw.items() if k not in ("type", "id")}
            step_id = raw.get("id") or f"{step_type}_{idx}"
            step = Step(type=step_type, params=params, id=step_id)

            if step_type in STEP_DECOMPOSERS:
                # Composite step: expand into multiple atomic steps
                expanded = STEP_DECOMPOSERS[step_type](step)
                steps.extend(expanded)
            else:
                steps.append(step)

        # Preserve top-level IR metadata (name, description, assumptions)
        metadata = {k: v for k, v in ir.items() if k != "steps"}
        return Workflow(steps=steps, metadata=metadata)
