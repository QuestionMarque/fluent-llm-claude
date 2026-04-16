"""LLM backends — the swappable layer underneath LLMClient.

A backend is anything that can turn a chat-style message list into a raw
text response. Two are shipped:

- `OpenAIBackend` — calls the OpenAI Chat Completions API with structured
  JSON response format. Requires `openai` installed and an API key.

- `DemoBackend` — returns canned responses from a scripted list. Used by
  `demo_llm.py` and tests so the LLM scenario (including the validation
  feedback loop) can be run without any network or API key.

New providers (Anthropic, Azure, local llama.cpp, ...) are added by
writing a new class that implements the `LLMBackend` protocol.
"""
from __future__ import annotations

import os
from typing import Any, Callable, Dict, List, Optional, Protocol, Union


Message = Dict[str, str]


class LLMBackendError(Exception):
    pass


class LLMBackend(Protocol):
    """Minimal contract every provider backend must satisfy."""

    name: str

    def complete(self, messages: List[Message]) -> str:
        """Send a message list and return the raw text response."""
        ...


# ---------------------------------------------------------------------------
# OpenAI
# ---------------------------------------------------------------------------

class OpenAIBackend:
    """OpenAI Chat Completions backend with JSON-object response format."""

    name = "openai"

    def __init__(
        self,
        model: str = "gpt-4o-mini",
        api_key: Optional[str] = None,
        temperature: float = 0.0,
    ):
        self.model = model
        self.temperature = temperature
        self.api_key = api_key or os.environ.get("OPENAI_API_KEY")
        if not self.api_key:
            raise LLMBackendError(
                "OPENAI_API_KEY is not set. Export it or pass api_key=... "
                "explicitly. For a no-key demo, use DemoBackend instead."
            )
        try:
            import openai
        except ImportError as e:
            raise LLMBackendError(
                "openai package is not installed. Run: pip install openai"
            ) from e
        self._client = openai.OpenAI(api_key=self.api_key)

    def complete(self, messages: List[Message]) -> str:
        response = self._client.chat.completions.create(
            model=self.model,
            messages=messages,
            response_format={"type": "json_object"},
            temperature=self.temperature,
        )
        return response.choices[0].message.content


# ---------------------------------------------------------------------------
# Demo (scripted)
# ---------------------------------------------------------------------------

Script = Union[str, Dict[str, Any]]
Responder = Callable[[List[Message]], Script]


class DemoBackend:
    """Scripted backend — returns prepared responses in order.

    Accepts either:
      - a list of responses (str or dict): popped in order per call
      - a callable: invoked with the current messages list, returns a response

    Responses that are dicts are JSON-serialized so the LLMClient's JSON
    parser round-trips cleanly. This is what makes the demo look exactly
    like a real LLM call.

    Typical use — showcase the feedback loop with a first-shot-wrong,
    second-shot-correct script:

        demo = DemoBackend(script=[
            {"steps": [{"type": "reagent_distribution", "params": {}}]},   # intentionally bad
            {"steps": [<fully valid IR here>]},                            # corrected after feedback
        ])
    """

    name = "demo"

    def __init__(
        self,
        script: Optional[Union[List[Script], Responder]] = None,
    ):
        if script is None:
            raise LLMBackendError(
                "DemoBackend needs a script (list of responses or a callable)."
            )
        self._script = script
        self._cursor = 0
        self.calls: List[List[Message]] = []   # recorded calls, for tests

    def complete(self, messages: List[Message]) -> str:
        # Record a defensive copy of what the caller sent.
        self.calls.append([dict(m) for m in messages])

        if callable(self._script):
            response = self._script(messages)
        else:
            if self._cursor >= len(self._script):
                raise LLMBackendError(
                    f"DemoBackend script exhausted after {self._cursor} call(s). "
                    "Provide more responses or a callable script."
                )
            response = self._script[self._cursor]
            self._cursor += 1

        if isinstance(response, (dict, list)):
            import json as _json
            return _json.dumps(response)
        return str(response)
