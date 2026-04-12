# llm/

Optional LLM integration for IFU → IR generation.
**The system runs fully in library mode without this package.**
Only instantiate `LLMClient` when `ir_mode="llm"`.

---

## Modules

### `llm_client.py`
`LLMClient` — calls an LLM provider to generate an IR from a prompt.

- Supports: OpenAI (`provider="openai"`)
- Enforces structured JSON output via `response_format={"type": "json_object"}`
- Retries up to `max_json_retries` times on JSON parse failures
- Raises `StructuredJSONError` after exhausting retries

**Extending to other providers:**
Add a branch in `_call_provider()` and a corresponding `_init_<provider>()`.

### `prompt_builder.py`
`PromptBuilder` — constructs complete prompts for IFU → IR generation.

Injects capability context from the registry so the LLM:
- Knows which step types exist (with required/optional fields)
- Knows which tip types, liquid classes, and labware are available
- Produces schema-valid, registry-grounded IR output

### `schema.py`
`IR_SCHEMA` — lightweight JSON schema for LLM output structure validation.
Confirms the response has a `steps` list before handing it to the decomposer.
Deep validation (required fields, step types) happens in `ValidatorWrapper`.

---

## LLM Mode Flow

```
IFU text
  ↓
PromptBuilder.build(ifu_text, context)
  ↓ (prompt string)
LLMClient.generate_ir(prompt)
  ↓ (IR dict or StructuredJSONError)
ExecutionLoop validates → retries with corrective prompt if invalid
```

---

## Minimal Usage

```python
import os
from execution_engine.llm.llm_client import LLMClient
from execution_engine.llm.prompt_builder import PromptBuilder
from execution_engine.capability_registry.loader import load_default_registry

os.environ["OPENAI_API_KEY"] = "sk-..."

registry = load_default_registry()
builder = PromptBuilder(registry=registry)
client = LLMClient(provider="openai", model="gpt-4o-mini")

ifu = "Distribute 100 µL of PBS buffer into all wells of a 96-well plate."
prompt = builder.build(ifu)
ir = client.generate_ir(prompt)
print(ir)  # {"steps": [...]}
```
