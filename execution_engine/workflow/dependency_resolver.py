"""Extension hook for future dependency-based workflow ordering.

Currently the system is linear — steps execute in their declared order.
This module is the designated location for future DAG-based dependency
resolution when loop/branch support is added.

To activate:
1. Add a 'depends_on: List[str]' field to the Step dataclass.
2. Implement resolve() to topologically sort workflow.steps by dependency.
3. Wire the resolver into WorkflowDecomposer or ExecutionLoop.run().

For now this module is a documented no-op — it returns steps as-is.
"""
from typing import List

from ..models.workflow import Step, Workflow


class DependencyResolver:
    """Placeholder for future dependency-based step ordering.

    Currently returns steps in their original declaration order.
    """

    def resolve(self, workflow: Workflow) -> List[Step]:
        """Return steps in execution order. Currently linear (no-op)."""
        return list(workflow.steps)
