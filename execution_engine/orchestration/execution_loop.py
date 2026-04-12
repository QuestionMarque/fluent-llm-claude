from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Union

from ..models.workflow import Workflow
from ..models.plan import Plan
from ..models.state import State
from ..models.feedback import ValidationFeedback
from ..workflow.decomposer import WorkflowDecomposer
from ..workflow.state_manager import StateManager
from ..validation.validator_wrapper import ValidatorWrapper
from ..validation.feedback_builder import FeedbackBuilder
from ..planner.planner import Planner
from ..runtime.pyfluent_adapter import PyFluentAdapter
from . import tdf_library


@dataclass
class ExecutionLoopResult:
    """Complete record of a single execution loop run."""
    success: bool
    attempts: int
    workflow: Optional[Workflow] = None
    plans: List[Plan] = field(default_factory=list)
    execution_log: List[Dict[str, Any]] = field(default_factory=list)
    error: Optional[str] = None
    retry_prompt: Optional[str] = None
    state: Optional[State] = None
    validation_feedback: Optional[ValidationFeedback] = None


class ExecutionLoop:
    """Control tower — coordinates end-to-end workflow execution.

    Modes:
    - tdf_mode="library": load TDF from tdf_library (fail-fast on validation errors)
    - tdf_mode="llm":     generate TDF via LLM, retry with corrective prompt on failure

    The difference in error handling between modes is intentional:
    - Library mode: the TDF is authored and should always be valid. Any failure
      is a code bug, not a runtime condition — fail immediately without retrying.
    - LLM mode: the model output may be imperfect. Build a retry prompt from
      the validation feedback and loop until valid or max_retries is hit.
    """

    def __init__(
        self,
        planner: Planner,
        runtime_adapter: PyFluentAdapter,
        validator: ValidatorWrapper,
        decomposer: Optional[WorkflowDecomposer] = None,
        llm_client=None,
        tdf_mode: str = "library",
        max_retries: int = 3,
    ):
        self.planner = planner
        self.runtime_adapter = runtime_adapter
        self.validator = validator
        self.decomposer = decomposer or WorkflowDecomposer()
        self.llm_client = llm_client
        self.tdf_mode = tdf_mode
        self.max_retries = max_retries
        self.feedback_builder = FeedbackBuilder()

    def run(self, prompt: str = "", tdf_name: str = "") -> ExecutionLoopResult:
        """Execute a full workflow from a TDF library name or LLM prompt."""
        retry_prompt = prompt
        last_feedback: Optional[ValidationFeedback] = None

        for attempt in range(1, self.max_retries + 2):
            print(f"\n[ExecutionLoop] Attempt {attempt}")

            # Step 1: Obtain TDF
            try:
                tdf = self._obtain_tdf(retry_prompt, tdf_name)
            except Exception as e:
                return ExecutionLoopResult(
                    success=False,
                    attempts=attempt,
                    error=f"Failed to obtain TDF: {e}",
                )

            # Step 2: Decompose into Workflow (or use pre-built Workflow directly)
            tdf_or_workflow = tdf
            if isinstance(tdf_or_workflow, Workflow):
                # Trusted developer Workflow — skip decomposition and schema validation.
                # Semantic checks still run but are advisory-only: errors are logged,
                # never treated as fail-fast blocking conditions.
                workflow = tdf_or_workflow
                print(f"[ExecutionLoop] Using pre-built Workflow: {len(workflow.steps)} step(s)")
                feedback = self.validator.validate_workflow(workflow)
                last_feedback = feedback
                if feedback.errors:
                    print(
                        f"[ExecutionLoop] Advisory validation — "
                        f"{len(feedback.errors)} issue(s) noted (proceeding)"
                    )
            else:
                # Dict TDF — full decompose + schema + semantic validation pipeline.
                try:
                    workflow = self.decomposer.decompose(tdf_or_workflow)
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
                    if self.tdf_mode == "library":
                        # Fail-fast: dict library TDFs must always be valid.
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

            # Step 3: Plan → Execute → State update for each step
            plans: List[Plan] = []
            execution_log: List[Dict[str, Any]] = []
            state_manager = StateManager()
            had_error = False

            for step in workflow.steps:
                log_entry: Dict[str, Any] = {
                    "step_id": step.id,
                    "step_type": step.type,
                }

                # Plan
                try:
                    plan = self.planner.plan(step)
                    plans.append(plan)
                    log_entry["method_name"] = plan.method_name
                    log_entry["score"] = plan.score
                    log_entry["variables"] = plan.variables
                    print(f"  [Plan] {step.id} → {plan.method_name} (score={plan.score})")
                except Exception as e:
                    log_entry["error"] = f"Planning failed: {e}"
                    execution_log.append(log_entry)
                    print(f"  [Plan ERROR] {step.id}: {e}")
                    had_error = True
                    continue

                # Execute
                result = self.runtime_adapter.execute(plan.method_name, plan.variables)
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
                plans=plans,
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

    def _obtain_tdf(self, prompt: str, tdf_name: str) -> Union[Dict[str, Any], Workflow]:
        if self.tdf_mode == "library":
            if not tdf_name:
                raise ValueError("tdf_name must be provided when tdf_mode='library'.")
            return tdf_library.get_tdf(tdf_name)

        if self.tdf_mode == "llm":
            if self.llm_client is None:
                raise RuntimeError("llm_client is required when tdf_mode='llm'.")
            return self.llm_client.generate_tdf(prompt)

        raise ValueError(f"Unknown tdf_mode: '{self.tdf_mode}'")
