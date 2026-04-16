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


@dataclass
class Conversation:
    """Full message history of a single IFU → IR generation run.

    Exposed so IRGenerator can carry context across retry turns and so
    callers can inspect exactly what was exchanged.
    """
    messages: List[Message] = field(default_factory=list)
    responses: List[str] = field(default_factory=list)

    def copy(self) -> "Conversation":
        return Conversation(
            messages=copy.deepcopy(self.messages),
            responses=list(self.responses),
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
    ):
        if backend is None:
            raise LLMClientError("LLMClient needs a backend (see llm.backends).")
        self.backend = backend
        self.max_json_retries = max_json_retries

    # ------------------------------------------------------------------
    # Factories
    # ------------------------------------------------------------------

    @classmethod
    def from_env(
        cls,
        demo_script: Optional[List[Any]] = None,
        max_json_retries: int = 3,
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

        return cls(backend=backend, max_json_retries=max_json_retries)

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
        backend for a new response. The conversation grows in place."""
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
