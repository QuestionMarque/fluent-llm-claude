from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Union
import asyncio
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
class PreparedWorkflow:
    """Result of the preparation phase (everything before execution).

    Produced by ExecutionLoop.prepare(). Contains the validated workflow
    and the list of RuntimeCalls that would be sent to the runtime
    adapter on execution. Safe to serialize and hand off to a separate
    executor — see `runtime_calls_to_dict_list` for JSON export.
    """
    success: bool
    attempts: int
    workflow: Optional[Workflow] = None
    runtime_calls: List[RuntimeCall] = field(default_factory=list)
    validation_feedback: Optional[ValidationFeedback] = None
    error: Optional[str] = None
    retry_prompt: Optional[str] = None


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

    Two phases:

    - `prepare()` is synchronous and backend-free. It obtains the IR,
      decomposes it, validates it, and builds the list of RuntimeCalls
      that would be sent to a runtime adapter. Use this when you only
      want the portable JSON artifact and don't want to touch hardware.

    - `run()` is async. It calls `prepare()` and then drives the
      runtime adapter to execute each RuntimeCall in order, updating
      state along the way. `run_sync()` is a blocking wrapper for
      CLI demos and tests.

    Modes:
    - ir_mode="library": load IR from IR_examples/ (fail-fast on validation errors)
    - ir_mode="llm":     generate IR via LLM, retry with corrective prompt on failure

    Because every step type maps to exactly one method in the registry, no
    planning is required — once validation passes, each step is converted
    directly into a RuntimeCall (`RuntimeCall.from_step(step, registry)`)
    and executed.
    """

    def __init__(
        self,
        registry: CapabilityRegistry,
        validator: ValidatorWrapper,
        runtime_adapter: Optional[PyFluentAdapter] = None,
        decomposer: Optional[WorkflowDecomposer] = None,
        ir_generator=None,
        ir_mode: str = "library",
        max_retries: int = 3,
    ):
        self.registry = registry
        self.validator = validator
        self.runtime_adapter = runtime_adapter
        self.decomposer = decomposer or WorkflowDecomposer()
        # ir_generator is an llm.IRGenerator-compatible object. We
        # accept it by duck type to avoid a hard import of the llm
        # package in library-mode users.
        self.ir_generator = ir_generator
        self.ir_mode = ir_mode
        self.max_retries = max_retries
        self.feedback_builder = FeedbackBuilder()

    # ------------------------------------------------------------------
    # Phase 1 — preparation (sync, backend-free)
    # ------------------------------------------------------------------

    def prepare(self, prompt: str = "", ir_name: str = "") -> PreparedWorkflow:
        """Obtain IR → Workflow → validate → build RuntimeCalls.

        Mode-dependent:
        - library: load an IR JSON from disk, validate once (fail-fast).
        - llm:     delegate to the IRGenerator, which drives a
                   multi-turn feedback loop until the IR validates.

        No hardware touched, no state updates. Safe to call without a
        runtime adapter configured.
        """
        if self.ir_mode == "library":
            return self._prepare_library(ir_name)
        if self.ir_mode == "llm":
            return self._prepare_llm(prompt)
        return PreparedWorkflow(
            success=False,
            attempts=0,
            error=f"Unknown ir_mode: '{self.ir_mode}'",
        )

    def _prepare_library(self, ir_name: str) -> PreparedWorkflow:
        print("\n[ExecutionLoop] Library mode")
        try:
            ir = self._load_library_ir(ir_name)
        except Exception as e:
            return PreparedWorkflow(
                success=False,
                attempts=1,
                error=f"Failed to obtain IR: {e}",
            )

        if isinstance(ir, Workflow):
            workflow = ir
            print(f"[ExecutionLoop] Using pre-built Workflow: {len(workflow.steps)} step(s)")
            feedback = self.validator.validate_workflow(workflow)
            if feedback.errors:
                print(
                    f"[ExecutionLoop] Advisory validation — "
                    f"{len(feedback.errors)} issue(s) noted (proceeding)"
                )
        else:
            try:
                workflow = self.decomposer.decompose(ir)
                print(f"[ExecutionLoop] Decomposed {len(workflow.steps)} step(s)")
            except Exception as e:
                return PreparedWorkflow(
                    success=False,
                    attempts=1,
                    error=f"Workflow decomposition failed: {e}",
                )

            feedback = self.validator.validate_workflow(workflow)
            print(f"[ExecutionLoop] Validation: {self.feedback_builder.summarize(feedback)}")

            if not feedback.is_valid:
                # Library IRs are authored and must always validate.
                return PreparedWorkflow(
                    success=False,
                    attempts=1,
                    workflow=workflow,
                    error="Validation failed in library mode (fail-fast). This is a code bug.",
                    validation_feedback=feedback,
                )

        return self._finalize_runtime_calls(workflow, feedback, attempts=1)

    def _prepare_llm(self, ifu_text: str) -> PreparedWorkflow:
        print("\n[ExecutionLoop] LLM mode")
        if self.ir_generator is None:
            return PreparedWorkflow(
                success=False,
                attempts=0,
                error=(
                    "ir_mode='llm' requires an ir_generator. Construct one with "
                    "execution_engine.llm.IRGenerator and pass it to ExecutionLoop."
                ),
            )
        if not ifu_text:
            return PreparedWorkflow(
                success=False,
                attempts=0,
                error="Empty prompt / IFU text in LLM mode.",
            )

        result = self.ir_generator.generate(ifu_text)

        if not result.success or result.workflow is None:
            return PreparedWorkflow(
                success=False,
                attempts=result.attempts,
                workflow=result.workflow,
                validation_feedback=result.validation_feedback,
                error=result.error or "IR generation did not produce a valid workflow.",
            )

        return self._finalize_runtime_calls(
            result.workflow, result.validation_feedback, attempts=result.attempts
        )

    def _finalize_runtime_calls(
        self,
        workflow: Workflow,
        feedback: Optional[ValidationFeedback],
        attempts: int,
    ) -> PreparedWorkflow:
        runtime_calls: List[RuntimeCall] = []
        for step in workflow.steps:
            try:
                runtime_calls.append(RuntimeCall.from_step(step, self.registry))
            except Exception as e:
                return PreparedWorkflow(
                    success=False,
                    attempts=attempts,
                    workflow=workflow,
                    validation_feedback=feedback,
                    error=f"Building runtime call for '{step.id}' failed: {e}",
                )

        return PreparedWorkflow(
            success=True,
            attempts=attempts,
            workflow=workflow,
            runtime_calls=runtime_calls,
            validation_feedback=feedback,
        )

    # ------------------------------------------------------------------
    # Phase 2 — execution (async)
    # ------------------------------------------------------------------

    async def run(self, prompt: str = "", ir_name: str = "") -> ExecutionLoopResult:
        """Full pipeline: prepare + execute.

        Requires a runtime_adapter. Use `run_sync` from blocking contexts.
        """
        if self.runtime_adapter is None:
            raise RuntimeError(
                "ExecutionLoop.run() requires a runtime_adapter. "
                "Call ExecutionLoop.prepare() if you only need the "
                "prepared workflow (no execution)."
            )

        prepared = self.prepare(prompt=prompt, ir_name=ir_name)
        if not prepared.success:
            return ExecutionLoopResult(
                success=False,
                attempts=prepared.attempts,
                workflow=prepared.workflow,
                runtime_calls=prepared.runtime_calls,
                error=prepared.error,
                retry_prompt=prepared.retry_prompt,
                validation_feedback=prepared.validation_feedback,
            )

        execution_log: List[Dict[str, Any]] = []
        state_manager = StateManager()
        had_error = False

        for step, call in zip(prepared.workflow.steps, prepared.runtime_calls):
            log_entry: Dict[str, Any] = {
                "step_id": step.id,
                "step_type": step.type,
                "method_name": call.method_name,
                "variables": call.variables,
            }

            result = await self.runtime_adapter.execute(call)
            log_entry["execution_success"] = result.success
            if not result.success:
                log_entry["error"] = result.error
                print(f"  [Execute ERROR] {step.id}: {result.error}")
                had_error = True
            else:
                print(f"  [Execute OK] {step.id} → {call.method_name}")

            state_manager.update(step, result.success)
            execution_log.append(log_entry)

        return ExecutionLoopResult(
            success=not had_error,
            attempts=prepared.attempts,
            workflow=prepared.workflow,
            runtime_calls=prepared.runtime_calls,
            execution_log=execution_log,
            state=state_manager.get_state(),
            validation_feedback=prepared.validation_feedback,
        )

    def run_sync(self, prompt: str = "", ir_name: str = "") -> ExecutionLoopResult:
        """Blocking wrapper around run() for CLI demos and tests."""
        return asyncio.run(self.run(prompt=prompt, ir_name=ir_name))

    # ------------------------------------------------------------------
    # IR loading
    # ------------------------------------------------------------------

    def _load_library_ir(self, ir_name: str) -> Union[Dict[str, Any], Workflow]:
        if not ir_name:
            raise ValueError("ir_name must be provided when ir_mode='library'.")
        base_path = Path(__file__).resolve().parent
        file_path = base_path / "IR_examples" / f"{ir_name}.json"
        if not file_path.exists():
            raise ValueError(f"IR '{ir_name}' not found in IR_examples")
        with open(file_path, "r") as f:
            return json.load(f)


# ---------------------------------------------------------------------------
# Portable-format helper
# ---------------------------------------------------------------------------

def runtime_calls_to_dict_list(calls: List[RuntimeCall]) -> List[Dict[str, Any]]:
    """Serialize RuntimeCalls to plain dicts (JSON-ready).

    This is the portable wire format between the planning/validation
    pipeline and whatever backend executes the workflow (PyFluent,
    direct VisionX, a simulator, a queue, a file on disk, etc.).
    """
    return [
        {
            "step_id": call.step_id,
            "method_name": call.method_name,
            "variables": call.variables,
        }
        for call in calls
    ]
