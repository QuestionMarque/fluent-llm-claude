# llm/

Natural-language IFU → validated IR, with a multi-turn feedback loop
back to the LLM when the first attempt doesn't pass validation.

**Optional.** Library-mode callers (`ir_mode="library"`) never touch
this package. Import it only when you want LLM-generated IR.

---

## Architecture

```
IFU text
  │
  ▼
PromptBuilder.build(ifu, registry)                → initial prompt
  │
  ▼
IRGenerator.generate(ifu)                         ← multi-turn loop
  │    │
  │    ├─ LLMClient.complete_conversation(conv)
  │    │     └─ LLMBackend (OpenAIBackend | DemoBackend | …)
  │    │
  │    ├─ WorkflowDecomposer.decompose(ir)
  │    │
  │    ├─ ValidatorWrapper.validate_workflow(wf)
  │    │
  │    └─ if invalid & retries remain:
  │           FeedbackBuilder.build_retry_prompt(feedback)
  │           LLMClient.continue_with(conv, feedback_message)
  │           loop.
  ▼
IRGenerationResult { success, attempts, ir, workflow, feedback, conversation }
```

The feedback loop is a **proper multi-turn chat**: each retry appends a
new `user` message with the validation report to the existing
conversation, so the model sees (a) the original IFU, (b) its own prior
assistant turn, and (c) a structured explanation of what went wrong.
This is a significant improvement over the previous flat-prompt retry
that reconstructed a fresh prompt on every attempt.

---

## Modules

### `backends.py`
- `LLMBackend` — minimal Protocol: `complete(messages) -> raw_text`.
- `OpenAIBackend` — wraps OpenAI Chat Completions with structured JSON
  response format. Requires `openai` installed and an API key.
- `DemoBackend` — scripted responses for tests and the no-key demo.
  Accepts either a list of responses (popped in order) or a callable.

### `llm_client.py`
`LLMClient` — provider-agnostic façade over a backend.

- `LLMClient(backend=..., max_json_retries=3, max_feedback_turns=5)`
- `LLMClient.from_env(demo_script=None)` — reads `LLM_PROVIDER`,
  `LLM_MODEL`, `OPENAI_API_KEY` from environment.
- `generate_ir(prompt)` — single-turn convenience.
- `start_conversation(user, system)` → `Conversation`
- `complete_conversation(conv)` — sends current messages, parses JSON,
  appends assistant turn. Retries JSON-parse failures only.
- `continue_with(conv, user_msg)` — appends a follow-up user turn and
  asks the backend for a new response. This is what drives the
  feedback loop. Increments `conv.feedback_turns`; raises
  `FeedbackBudgetExceededError` *before* contacting the backend if the
  per-conversation budget would be exceeded.

#### Feedback-loop budget

`max_feedback_turns` (default 5) is a **hard safety guard** on the
number of `continue_with` calls allowed against any one Conversation.
It exists to prevent a misbehaving caller — or an LLM that never
converges — from looping indefinitely and burning tokens.

- The counter (`Conversation.feedback_turns`) lives on the
  Conversation, so `start_conversation` resets it.
- The check happens *before* the backend call, so an exhausted budget
  costs zero extra tokens.
- `IRGenerator` catches `FeedbackBudgetExceededError` and returns a
  failed `IRGenerationResult` rather than propagating, so the executor
  always sees a clean result even at the safety boundary.
- Choose values consistent with each other: `IRGenerator.max_retries`
  ≤ `LLMClient.max_feedback_turns`.

### `ir_generator.py`
`IRGenerator` — the orchestrator that owns the IFU → validated IR
pipeline end-to-end. Used by `ExecutionLoop` when `ir_mode="llm"`.

### `prompt_builder.py`
`PromptBuilder` — injects capability context (step schema, available
tips, liquid classes, labware) so the LLM can generate registry-grounded
IR rather than hallucinating names.

### `schema.py`
`IR_SCHEMA` — lightweight shape check. Deep validation is
`ValidatorWrapper`'s job.

---

## Environment variables

| Variable         | Used by                 | Default         |
|------------------|-------------------------|-----------------|
| `LLM_PROVIDER`   | `LLMClient.from_env`    | `openai`        |
| `LLM_MODEL`      | `OpenAIBackend`         | `gpt-4o-mini`   |
| `OPENAI_API_KEY` | `OpenAIBackend`         | *(required)*    |

For the `demo` provider no env var is required; just pass
`demo_script=[…]` explicitly.

---

## Demo (no API key required)

```
python demo_llm.py
```

`demo_llm.py` uses a `DemoBackend` scripted to return a deliberately
incomplete IR first, so you can watch the validation feedback loop kick
in. The second scripted response is correct and the run finishes with a
valid, registry-grounded IR plus the portable JSON artifact.

To run against a real provider instead:

```
export LLM_PROVIDER=openai
export LLM_MODEL=gpt-4o-mini
export OPENAI_API_KEY=sk-...
python demo_llm.py --provider env
```

---

## Adding a new provider

1. Write a new class in `backends.py` that satisfies the `LLMBackend`
   Protocol (has a `name` attribute and a `complete(messages)` method).
2. Add a branch in `LLMClient.from_env` keyed on `LLM_PROVIDER`.
3. Export it from `llm/__init__.py`.

Everything else in the pipeline is provider-agnostic.

---

## Minimal Usage

```python
from execution_engine.capability_registry.loader import load_default_registry
from execution_engine.llm import DemoBackend, IRGenerator, LLMClient, PromptBuilder
from execution_engine.validation.validator_wrapper import ValidatorWrapper

registry = load_default_registry()
client = LLMClient(backend=DemoBackend(script=[YOUR_IR_DICT]))
gen = IRGenerator(
    client=client,
    prompt_builder=PromptBuilder(registry=registry),
    validator=ValidatorWrapper(registry=registry),
    max_retries=3,
)

result = gen.generate("Distribute 100 µL of Buffer into all 96 wells.")
if result.success:
    workflow = result.workflow        # typed Workflow ready to execute
    ir = result.ir                    # dict IR for audit
    conv = result.conversation        # full chat history
else:
    feedback = result.validation_feedback
```
