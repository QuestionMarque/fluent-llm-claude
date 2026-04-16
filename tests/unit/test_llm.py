"""Tests for the LLM package — backends, client, and IR feedback loop."""
import json
import os

import pytest

from execution_engine.capability_registry.loader import load_default_registry
from execution_engine.llm import (
    DemoBackend,
    IRGenerator,
    LLMBackendError,
    LLMClient,
    LLMClientError,
    PromptBuilder,
)
from execution_engine.llm.llm_client import StructuredJSONError
from execution_engine.validation.validator_wrapper import ValidatorWrapper


# --- Fixtures -------------------------------------------------------------

@pytest.fixture
def registry():
    return load_default_registry()


@pytest.fixture
def prompt_builder(registry):
    return PromptBuilder(registry=registry)


@pytest.fixture
def validator(registry):
    return ValidatorWrapper(registry=registry)


@pytest.fixture(autouse=True)
def clear_llm_env(monkeypatch):
    """Keep process-level LLM_* env state out of each test."""
    for var in ("LLM_PROVIDER", "LLM_MODEL", "OPENAI_API_KEY"):
        monkeypatch.delenv(var, raising=False)


# --- Backends -------------------------------------------------------------

class TestDemoBackend:
    def test_requires_a_script(self):
        with pytest.raises(LLMBackendError):
            DemoBackend(script=None)

    def test_returns_scripted_responses_in_order(self):
        backend = DemoBackend(script=[{"a": 1}, {"b": 2}])
        first = backend.complete([{"role": "user", "content": "hi"}])
        second = backend.complete([{"role": "user", "content": "hi"}])
        assert json.loads(first) == {"a": 1}
        assert json.loads(second) == {"b": 2}

    def test_raises_when_script_exhausted(self):
        backend = DemoBackend(script=[{"x": 1}])
        backend.complete([])
        with pytest.raises(LLMBackendError):
            backend.complete([])

    def test_callable_script_sees_messages(self):
        seen = []

        def responder(messages):
            seen.append(len(messages))
            return {"got": seen[-1]}

        backend = DemoBackend(script=responder)
        backend.complete([{"role": "user", "content": "m1"}])
        backend.complete([{"role": "user", "content": "m1"},
                          {"role": "assistant", "content": "a"}])
        assert seen == [1, 2]

    def test_records_calls_for_inspection(self):
        backend = DemoBackend(script=[{"ok": True}])
        backend.complete([{"role": "user", "content": "hello"}])
        assert len(backend.calls) == 1
        assert backend.calls[0][0]["content"] == "hello"


# --- LLMClient ------------------------------------------------------------

class TestLLMClient:
    def test_requires_backend(self):
        with pytest.raises(LLMClientError):
            LLMClient(backend=None)

    def test_generate_ir_single_turn(self):
        backend = DemoBackend(script=[{"steps": []}])
        client = LLMClient(backend=backend)
        ir = client.generate_ir("any prompt")
        assert ir == {"steps": []}

    def test_retries_on_unparseable_json(self):
        backend = DemoBackend(script=["not json at all", {"steps": []}])
        client = LLMClient(backend=backend, max_json_retries=3)
        ir = client.generate_ir("prompt")
        assert ir == {"steps": []}

    def test_raises_after_exhausting_retries(self):
        backend = DemoBackend(script=["garbage", "still garbage"])
        client = LLMClient(backend=backend, max_json_retries=2)
        with pytest.raises(StructuredJSONError):
            client.generate_ir("prompt")

    def test_continue_with_appends_feedback_turn(self):
        backend = DemoBackend(script=[{"v": 1}, {"v": 2}])
        client = LLMClient(backend=backend)
        conv = client.start_conversation("hello", system_prompt="sys")
        first = client.complete_conversation(conv)
        assert first == {"v": 1}
        second = client.continue_with(conv, "here is feedback")
        assert second == {"v": 2}
        # Conversation should now contain: system, user, assistant, user (feedback), assistant
        roles = [m["role"] for m in conv.messages]
        assert roles == ["system", "user", "assistant", "user", "assistant"]
        # The second backend call should have seen the full history.
        assert len(backend.calls) == 2
        assert len(backend.calls[-1]) == 4  # system + user + assistant + user

    def test_from_env_defaults_to_openai(self, monkeypatch):
        # No OPENAI_API_KEY — should fail with a helpful error.
        with pytest.raises(LLMBackendError):
            LLMClient.from_env()

    def test_from_env_rejects_unknown_provider(self, monkeypatch):
        monkeypatch.setenv("LLM_PROVIDER", "mystery")
        with pytest.raises(LLMClientError):
            LLMClient.from_env()

    def test_from_env_demo_requires_script(self, monkeypatch):
        monkeypatch.setenv("LLM_PROVIDER", "demo")
        with pytest.raises(LLMClientError):
            LLMClient.from_env()

    def test_from_env_demo_with_script(self, monkeypatch):
        monkeypatch.setenv("LLM_PROVIDER", "demo")
        client = LLMClient.from_env(demo_script=[{"ok": True}])
        assert client.backend.name == "demo"
        assert client.generate_ir("x") == {"ok": True}


# --- IRGenerator feedback loop -------------------------------------------

VALID_IR = {
    "steps": [
        {
            "id": "s0",
            "type": "get_tips",
            "params": {"diti_type": "DiTi_200uL"},
        },
        {
            "id": "s1",
            "type": "drop_tips_to_location",
            "params": {"labware": "Waste_Container"},
        },
    ],
}

FLAWED_IR = {
    "steps": [
        {
            "id": "s0",
            "type": "get_tips",
            "params": {},    # missing required diti_type
        },
    ],
}


class TestIRGenerator:
    def test_first_attempt_valid_returns_success_in_one_attempt(
        self, prompt_builder, validator
    ):
        client = LLMClient(backend=DemoBackend(script=[VALID_IR]))
        gen = IRGenerator(
            client=client,
            prompt_builder=prompt_builder,
            validator=validator,
            max_retries=2,
        )
        result = gen.generate("any IFU")
        assert result.success
        assert result.attempts == 1
        assert result.workflow is not None
        assert len(result.workflow.steps) == 2

    def test_feedback_loop_recovers_on_second_turn(
        self, prompt_builder, validator
    ):
        backend = DemoBackend(script=[FLAWED_IR, VALID_IR])
        client = LLMClient(backend=backend)
        gen = IRGenerator(
            client=client,
            prompt_builder=prompt_builder,
            validator=validator,
            max_retries=2,
        )
        result = gen.generate("any IFU")
        assert result.success
        assert result.attempts == 2
        # Second backend call should have seen the feedback turn.
        assert len(backend.calls) == 2
        roles_in_second_call = [m["role"] for m in backend.calls[1]]
        assert roles_in_second_call[-1] == "user"  # feedback
        assert "failed validation" in backend.calls[1][-1]["content"].lower()

    def test_gives_up_after_max_retries(self, prompt_builder, validator):
        backend = DemoBackend(script=[FLAWED_IR, FLAWED_IR, FLAWED_IR])
        client = LLMClient(backend=backend)
        gen = IRGenerator(
            client=client,
            prompt_builder=prompt_builder,
            validator=validator,
            max_retries=2,
        )
        result = gen.generate("any IFU")
        assert not result.success
        assert result.validation_feedback is not None
        assert not result.validation_feedback.is_valid

    def test_conversation_is_returned_for_inspection(
        self, prompt_builder, validator
    ):
        backend = DemoBackend(script=[FLAWED_IR, VALID_IR])
        client = LLMClient(backend=backend)
        gen = IRGenerator(
            client=client,
            prompt_builder=prompt_builder,
            validator=validator,
            max_retries=2,
        )
        result = gen.generate("any IFU")
        assert result.conversation is not None
        # system + user(initial) + assistant + user(feedback) + assistant
        assert len(result.conversation.messages) == 5
