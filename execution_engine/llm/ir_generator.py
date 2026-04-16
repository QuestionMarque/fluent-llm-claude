"""IRGenerator — drives the IFU → validated IR feedback loop.

Orchestrates:
  1. Prompt construction from the IFU (PromptBuilder, registry-aware)
  2. LLM call (LLMClient + backend)
  3. Workflow decomposition (WorkflowDecomposer)
  4. Validation against schema + registry (ValidatorWrapper)
  5. If invalid and retries remain: feed the error report back into the
     same conversation and ask the LLM to revise.

This is the multi-turn replacement for the old flat retry prompt in
ExecutionLoop — the LLM sees its previous assistant turn *and* the
validation feedback in a proper chat sequence, which meaningfully
improves its ability to self-correct.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from ..models.feedback import ValidationFeedback
from ..models.workflow import Workflow
from ..validation.feedback_builder import FeedbackBuilder
from ..validation.validator_wrapper import ValidatorWrapper
from ..workflow.decomposer import WorkflowDecomposer
from .llm_client import Conversation, LLMClient, StructuredJSONError
from .prompt_builder import PromptBuilder


@dataclass
class IRGenerationResult:
    """Outcome of an IFU → validated IR run."""
    success: bool
    attempts: int
    ir: Optional[Dict[str, Any]] = None
    workflow: Optional[Workflow] = None
    validation_feedback: Optional[ValidationFeedback] = None
    conversation: Optional[Conversation] = None
    error: Optional[str] = None


class IRGenerator:
    """Turn a natural-language IFU into a validated IR.

    Usage:

        gen = IRGenerator(
            client=LLMClient.from_env(demo_script=[...]),
            prompt_builder=PromptBuilder(registry=registry),
            validator=ValidatorWrapper(registry=registry),
        )
        result = gen.generate(ifu_text)

        if result.success:
            feed result.workflow or result.ir into the execution pipeline
        else:
            inspect result.validation_feedback / result.conversation
    """

    def __init__(
        self,
        client: LLMClient,
        prompt_builder: PromptBuilder,
        validator: ValidatorWrapper,
        decomposer: Optional[WorkflowDecomposer] = None,
        feedback_builder: Optional[FeedbackBuilder] = None,
        max_retries: int = 3,
    ):
        self.client = client
        self.prompt_builder = prompt_builder
        self.validator = validator
        self.decomposer = decomposer or WorkflowDecomposer()
        self.feedback_builder = feedback_builder or FeedbackBuilder()
        self.max_retries = max_retries

    def generate(self, ifu_text: str, context: Optional[str] = None) -> IRGenerationResult:
        """IFU → validated IR with a multi-turn feedback loop."""
        user_prompt = self.prompt_builder.build(ifu_text, context=context)
        system_prompt = self.prompt_builder.SYSTEM_PROMPT

        conv = self.client.start_conversation(
            user_prompt=user_prompt,
            system_prompt=system_prompt,
        )

        last_feedback: Optional[ValidationFeedback] = None
        last_workflow: Optional[Workflow] = None
        last_ir: Optional[Dict[str, Any]] = None

        for attempt in range(1, self.max_retries + 2):
            print(f"\n[IRGenerator] Attempt {attempt}")

            # --- Ask the LLM ---
            try:
                if attempt == 1:
                    ir = self.client.complete_conversation(conv)
                else:
                    feedback_message = self.feedback_builder.build_retry_prompt(
                        last_feedback, original_prompt=""
                    )
                    ir = self.client.continue_with(conv, feedback_message)
            except StructuredJSONError as e:
                return IRGenerationResult(
                    success=False,
                    attempts=attempt,
                    conversation=conv,
                    error=f"LLM returned unparseable JSON: {e}",
                )

            last_ir = ir

            # --- Decompose ---
            try:
                workflow = self.decomposer.decompose(ir)
            except Exception as e:
                # A decomposition error is itself feedback the LLM can act
                # on. Synthesize a ValidationFeedback so the loop can retry.
                last_feedback = self._decomposition_as_feedback(e)
                print(f"[IRGenerator] Decomposition failed: {e}")
                if attempt > self.max_retries:
                    return IRGenerationResult(
                        success=False,
                        attempts=attempt,
                        ir=ir,
                        conversation=conv,
                        validation_feedback=last_feedback,
                        error=f"Decomposition failed after {self.max_retries} retry attempt(s): {e}",
                    )
                continue

            last_workflow = workflow

            # --- Validate ---
            feedback = self.validator.validate_workflow(workflow)
            last_feedback = feedback
            print(f"[IRGenerator] Validation: {self.feedback_builder.summarize(feedback)}")

            if feedback.is_valid:
                return IRGenerationResult(
                    success=True,
                    attempts=attempt,
                    ir=ir,
                    workflow=workflow,
                    validation_feedback=feedback,
                    conversation=conv,
                )

            if attempt > self.max_retries:
                return IRGenerationResult(
                    success=False,
                    attempts=attempt,
                    ir=ir,
                    workflow=workflow,
                    validation_feedback=feedback,
                    conversation=conv,
                    error=f"Validation failed after {self.max_retries} retry attempt(s).",
                )

            print("[IRGenerator] Validation failed — sending feedback back to the LLM...")

        # Unreachable (loop exits via return in each branch), but satisfies type checkers.
        return IRGenerationResult(
            success=False,
            attempts=self.max_retries + 1,
            ir=last_ir,
            workflow=last_workflow,
            validation_feedback=last_feedback,
            conversation=conv,
            error=f"Exhausted {self.max_retries} retry attempt(s).",
        )

    def _decomposition_as_feedback(self, error: Exception) -> ValidationFeedback:
        """Wrap a decomposition exception so it flows through the same
        feedback loop as schema/semantic validation errors."""
        from ..models.feedback import FeedbackItem
        return ValidationFeedback(
            errors=[FeedbackItem(
                type="decomposition_error",
                message=f"Workflow decomposition failed: {error}",
                suggestion="Ensure every step has a 'type' and the 'steps' list is well-formed.",
                severity="error",
            )]
        )
