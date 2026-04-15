from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Union
import json
from pathlib import Path

from ..models.workflow import Workflow
from ..models.runtime_call import RuntimeCall
from ..models.state import State
from ..models.feedback import ValidationFeedback
from ..workflow.decomposer import WorkflowDecomposer
from ..workflow.state_manager import StateManager
from ..validation.validator_wrapper import ValidatorWrapper
from ..validation.feedback_builder import FeedbackBuilder
from ..capability_registry.registry import CapabilityRegistry
from ..runtime.pyfluent_adapter import PyFluentAdapter


@dataclass
class ExecutionLoopResult:
    """Complete record of a single execution loop run."""
    success: bool
    attempts: int
    workflow: Optional[Workflow] = None
    runtime_calls: List[RuntimeCall] = field(default_factory=list)
    execution_log: List[Dict[str, Any]] = field(default_factory=list)
    error: Optional[str] = None
    retry_prompt: Optional[str] = None
    state: Optional[State] = None
    validation_feedback: Optional[ValidationFeedback] = None


class ExecutionLoop:
    """Control tower — coordinates end-to-end workflow execution.

    Modes:
    - ir_mode="library": load IR from IR_examples/ (fail-fast on validation errors)
    - ir_mode="llm":     generate IR via LLM, retry with corrective prompt on failure

    The difference in error handling between modes is intentional:
    - Library mode: the IR is authored and should always be valid. Any failure
      is a code bug, not a runtime condition — fail immediately without retrying.
    - LLM mode: the model output may be imperfect. Build a retry prompt from
      the validation feedback and loop until valid or max_retries is hit.

    Because every step type maps to exactly one method in the registry, no
    planning is required — once validation passes, each step is converted
    directly into a RuntimeCall (`RuntimeCall.from_step(step, registry)`)
    and executed.
    """

    def __init__(
        self,
        registry: CapabilityRegistry,
        runtime_adapter: PyFluentAdapter,
        validator: ValidatorWrapper,
        decomposer: Optional[WorkflowDecomposer] = None,
        llm_client=None,
        ir_mode: str = "library",
        max_retries: int = 3,
    ):
        self.registry = registry
        self.runtime_adapter = runtime_adapter
        self.validator = validator
        self.decomposer = decomposer or WorkflowDecomposer()
        self.llm_client = llm_client
        self.ir_mode = ir_mode
        self.max_retries = max_retries
        self.feedback_builder = FeedbackBuilder()

    def run(self, prompt: str = "", ir_name: str = "") -> ExecutionLoopResult:
        """Execute a full workflow from an IR library name or LLM prompt."""
        retry_prompt = prompt
        last_feedback: Optional[ValidationFeedback] = None

        for attempt in range(1, self.max_retries + 2):
            print(f"\n[ExecutionLoop] Attempt {attempt}")

            # Step 1: Obtain IR
            try:
                ir = self._obtain_ir(retry_prompt, ir_name)
            except Exception as e:
                return ExecutionLoopResult(
                    success=False,
                    attempts=attempt,
                    error=f"Failed to obtain IR: {e}",
                )

            # Step 2: Decompose into Workflow (or use pre-built Workflow directly)
            ir_or_workflow = ir
            if isinstance(ir_or_workflow, Workflow):
                # Trusted developer Workflow — skip decomposition and schema validation.
                # Semantic checks still run advisory-only: errors are logged,
                # never treated as fail-fast blocking conditions.
                workflow = ir_or_workflow
                print(f"[ExecutionLoop] Using pre-built Workflow: {len(workflow.steps)} step(s)")
                feedback = self.validator.validate_workflow(workflow)
                last_feedback = feedback
                if feedback.errors:
                    print(
                        f"[ExecutionLoop] Advisory validation — "
                        f"{len(feedback.errors)} issue(s) noted (proceeding)"
                    )
            else:
                # Dict IR — full decompose + schema + semantic validation pipeline.
                try:
                    workflow = self.decomposer.decompose(ir_or_workflow)
                    print(f"[ExecutionLoop] Decomposed {len(workflow.steps)} step(s)")
                except Exception as e:
                    return ExecutionLoopResult(
                        success=False,
                        attempts=attempt,
                        error=f"Workflow decomposition failed: {e}",
                    )

                feedback = self.validator.validate_workflow(workflow)
                last_feedback = feedback
                print(f"[ExecutionLoop] Validation: {self.feedback_builder.summarize(feedback)}")

                if not feedback.is_valid:
                    if self.ir_mode == "library":
                        # Fail-fast: dict library IRs must always be valid.
                        return ExecutionLoopResult(
                            success=False,
                            attempts=attempt,
                            workflow=workflow,
                            error="Validation failed in library mode (fail-fast). This is a code bug.",
                            validation_feedback=feedback,
                        )

                    # LLM mode: build corrective prompt and retry
                    retry_prompt = self.feedback_builder.build_retry_prompt(feedback, retry_prompt)
                    print("[ExecutionLoop] Validation failed — retrying with corrective prompt...")
                    continue

            # Step 3: Map → Execute → State update for each step
            runtime_calls: List[RuntimeCall] = []
            execution_log: List[Dict[str, Any]] = []
            state_manager = StateManager()
            had_error = False

            for step in workflow.steps:
                log_entry: Dict[str, Any] = {
                    "step_id": step.id,
                    "step_type": step.type,
                }

                # Build a concrete runtime call directly from the step
                try:
                    call = RuntimeCall.from_step(step, self.registry)
                    runtime_calls.append(call)
                    log_entry["method_name"] = call.method_name
                    log_entry["variables"] = call.variables
                    print(f"  [Build] {step.id} → {call.method_name}")
                except Exception as e:
                    log_entry["error"] = f"Building runtime call failed: {e}"
                    execution_log.append(log_entry)
                    print(f"  [Build ERROR] {step.id}: {e}")
                    had_error = True
                    continue

                # Execute
                result = self.runtime_adapter.execute(call.method_name, call.variables)
                log_entry["execution_success"] = result.success
                if not result.success:
                    log_entry["error"] = result.error
                    print(f"  [Execute ERROR] {step.id}: {result.error}")
                    had_error = True
                else:
                    print(f"  [Execute OK] {step.id}")

                # Update state
                state_manager.update(step, result.success)
                execution_log.append(log_entry)

            return ExecutionLoopResult(
                success=not had_error,
                attempts=attempt,
                workflow=workflow,
                runtime_calls=runtime_calls,
                execution_log=execution_log,
                state=state_manager.get_state(),
                validation_feedback=feedback,
            )

        # Exhausted all retries
        return ExecutionLoopResult(
            success=False,
            attempts=self.max_retries + 1,
            error=f"Exhausted {self.max_retries} retry attempt(s).",
            retry_prompt=retry_prompt,
            validation_feedback=last_feedback,
        )

    def _obtain_ir(self, prompt: str, ir_name: str) -> Union[Dict[str, Any], Workflow]:
        if self.ir_mode == "library":
            if not ir_name:
                raise ValueError("ir_name must be provided when ir_mode='library'.")

            base_path = Path(__file__).resolve().parent
            file_path = base_path / "IR_examples" / f"{ir_name}.json"

            if not file_path.exists():
                raise ValueError(f"IR '{ir_name}' not found in IR_examples")

            with open(file_path, "r") as f:
                generated_ir = json.load(f)

            return generated_ir

        if self.ir_mode == "llm":
            if self.llm_client is None:
                raise RuntimeError("llm_client is required when ir_mode='llm'.")
            return self.llm_client.generate_ir(prompt)

        raise ValueError(f"Unknown ir_mode: '{self.ir_mode}'")
