"""LLMClient — the façade in front of a swappable backend.

Responsibilities:
- Build the initial system+user message list from an IFU.
- Hand messages to a backend, parse the JSON response, retry on parse
  failure up to `max_json_retries` times.
- Offer `continue_with(feedback)` so the IRGenerator can extend the
  conversation with validation feedback and get a corrected response —
  as a proper multi-turn chat rather than a reconstructed flat prompt.

The OpenAI vs Demo vs future-provider choice lives entirely in the
backend; the client itself is provider-agnostic.
"""
from __future__ import annotations

import copy
import json
import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from .backends import DemoBackend, LLMBackend, LLMBackendError, Message, OpenAIBackend


class LLMClientError(Exception):
    pass


class StructuredJSONError(LLMClientError):
    pass


class FeedbackBudgetExceededError(LLMClientError):
    """Raised when LLMClient.continue_with is called past its configured
    `max_feedback_turns` budget for a single conversation.

    Hard safety guard against runaway feedback loops that would consume
    an unbounded number of tokens. Per-conversation: starts fresh with
    every `start_conversation`."""


@dataclass
class Conversation:
    """Full message history of a single IFU → IR generation run.

    Exposed so IRGenerator can carry context across retry turns and so
    callers can inspect exactly what was exchanged.

    `feedback_turns` counts the number of `LLMClient.continue_with`
    calls executed against this conversation. It's checked against
    `LLMClient.max_feedback_turns` to bound the feedback loop.
    """
    messages: List[Message] = field(default_factory=list)
    responses: List[str] = field(default_factory=list)
    feedback_turns: int = 0

    def copy(self) -> "Conversation":
        return Conversation(
            messages=copy.deepcopy(self.messages),
            responses=list(self.responses),
            feedback_turns=self.feedback_turns,
        )


class LLMClient:
    """Provider-agnostic wrapper around an `LLMBackend`.

    Instantiation:

        # Explicit
        client = LLMClient(backend=OpenAIBackend(model="gpt-4o-mini"))

        # Env-var driven (picks up LLM_PROVIDER / LLM_MODEL / OPENAI_API_KEY
        # and, if LLM_PROVIDER == "demo", an optional DEMO_IR file).
        client = LLMClient.from_env()

    Use `generate_ir(ifu_text, system_prompt)` for a one-shot generation.
    Use `start_conversation()` + `continue_with(feedback)` when you need
    multi-turn interaction — the IRGenerator takes this path.
    """

    def __init__(
        self,
        backend: LLMBackend,
        max_json_retries: int = 3,
        max_feedback_turns: int = 5,
    ):
        """
        Parameters
        ----------
        backend
            Provider-specific backend (OpenAIBackend, DemoBackend, …).
        max_json_retries
            How many times to re-ask the backend when its response is not
            valid JSON. Per `complete_conversation` call.
        max_feedback_turns
            Hard cap on the number of `continue_with` calls allowed on a
            single Conversation. Bounds the feedback loop so a misbehaving
            caller — or an LLM that never converges — cannot consume an
            unbounded number of tokens. Counted per Conversation; resets
            when `start_conversation` returns a fresh one.
        """
        if backend is None:
            raise LLMClientError("LLMClient needs a backend (see llm.backends).")
        if max_feedback_turns < 0:
            raise LLMClientError("max_feedback_turns must be >= 0.")
        self.backend = backend
        self.max_json_retries = max_json_retries
        self.max_feedback_turns = max_feedback_turns

    # ------------------------------------------------------------------
    # Factories
    # ------------------------------------------------------------------

    @classmethod
    def from_env(
        cls,
        demo_script: Optional[List[Any]] = None,
        max_json_retries: int = 3,
        max_feedback_turns: int = 5,
    ) -> "LLMClient":
        """Build a client from environment variables.

        Env vars:
          LLM_PROVIDER    one of {"openai", "demo"} (default: "openai")
          LLM_MODEL       provider-specific model id (default: "gpt-4o-mini")
          OPENAI_API_KEY  required for the openai provider

        For "demo", pass `demo_script` explicitly — there is no env-var
        hook for scripted responses because putting IR JSON in env vars
        would be unwieldy.
        """
        provider = os.environ.get("LLM_PROVIDER", "openai").lower()

        if provider == "openai":
            model = os.environ.get("LLM_MODEL", "gpt-4o-mini")
            backend: LLMBackend = OpenAIBackend(model=model)
        elif provider == "demo":
            if demo_script is None:
                raise LLMClientError(
                    "LLM_PROVIDER=demo requires a demo_script argument."
                )
            backend = DemoBackend(script=demo_script)
        else:
            raise LLMClientError(
                f"Unsupported LLM_PROVIDER={provider!r}. "
                "Supported: 'openai', 'demo'. Add a new backend in llm/backends.py."
            )

        return cls(
            backend=backend,
            max_json_retries=max_json_retries,
            max_feedback_turns=max_feedback_turns,
        )

    # ------------------------------------------------------------------
    # Single-turn
    # ------------------------------------------------------------------

    def generate_ir(self, prompt: str, system_prompt: Optional[str] = None) -> Dict[str, Any]:
        """Legacy single-turn helper. New code should prefer IRGenerator
        (multi-turn with a feedback loop)."""
        conv = self.start_conversation(prompt, system_prompt=system_prompt)
        return self.complete_conversation(conv)

    # ------------------------------------------------------------------
    # Multi-turn
    # ------------------------------------------------------------------

    def start_conversation(
        self,
        user_prompt: str,
        system_prompt: Optional[str] = None,
    ) -> Conversation:
        """Build the initial message list for a new IR generation run."""
        messages: List[Message] = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": user_prompt})
        return Conversation(messages=messages)

    def complete_conversation(self, conv: Conversation) -> Dict[str, Any]:
        """Send the current messages, parse JSON, and append the assistant
        turn to the conversation so the next call can continue from here.

        Retries on JSON parse failures (NOT on semantic validation —
        that's the IRGenerator's job)."""
        last_error: Optional[Exception] = None
        for attempt in range(1, self.max_json_retries + 1):
            try:
                raw = self.backend.complete(conv.messages)
            except LLMBackendError as e:
                raise LLMClientError(f"Backend error: {e}") from e

            conv.responses.append(raw)
            try:
                ir = self._parse_json(raw)
                conv.messages.append({"role": "assistant", "content": raw})
                return ir
            except StructuredJSONError as e:
                last_error = e
                print(f"[LLMClient] JSON parse error (attempt {attempt}): {e}")
                # Don't append the bad assistant turn — the retry asks
                # the same question with no poisoning from bad JSON.

        raise StructuredJSONError(
            f"Failed to obtain valid JSON after {self.max_json_retries} attempt(s). "
            f"Last error: {last_error}"
        )

    def continue_with(self, conv: Conversation, user_message: str) -> Dict[str, Any]:
        """Append a user turn (typically validation feedback) and ask the
        backend for a new response. The conversation grows in place.

        Enforces the per-conversation `max_feedback_turns` budget: if
        `conv.feedback_turns` is already at the cap, raises
        `FeedbackBudgetExceededError` *before* contacting the backend so
        no extra tokens are consumed. The counter is incremented only
        after the budget check passes.
        """
        if conv.feedback_turns >= self.max_feedback_turns:
            raise FeedbackBudgetExceededError(
                f"continue_with refused: feedback budget "
                f"({self.max_feedback_turns}) already exhausted for this "
                f"conversation. Increase max_feedback_turns or stop the loop."
            )
        conv.feedback_turns += 1
        conv.messages.append({"role": "user", "content": user_message})
        return self.complete_conversation(conv)

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _parse_json(self, raw: str) -> Dict[str, Any]:
        try:
            return json.loads(raw)
        except json.JSONDecodeError as e:
            raise StructuredJSONError(
                f"Invalid JSON from LLM: {e}\nContent snippet: {raw[:300]}"
            )
