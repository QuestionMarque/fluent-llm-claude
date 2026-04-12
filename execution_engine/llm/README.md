# llm/

Optional LLM integration for IFU → TDF generation.
**The system runs fully in library mode without this package.**
Only instantiate `LLMClient` when `tdf_mode="llm"`.

---

## Modules

### `llm_client.py`
`LLMClient` — calls an LLM provider to generate a TDF from a prompt.

- Supports: OpenAI (`provider="openai"`)
- Enforces structured JSON output via `response_format={"type": "json_object"}`
- Retries up to `max_json_retries` times on JSON parse failures
- Raises `StructuredJSONError` after exhausting retries

**Extending to other providers:**
Add a branch in `_call_provider()` and a corresponding `_init_<provider>()`.

### `prompt_builder.py`
`PromptBuilder` — constructs complete prompts for IFU → TDF generation.

Injects capability context from the registry so the LLM:
- Knows which step types exist (with required/optional fields)
- Knows which tip types, liquid classes, and labware are available
- Produces schema-valid, registry-grounded TDF output

### `schema.py`
`TDF_SCHEMA` — lightweight JSON schema for LLM output structure validation.
Confirms the response has a `steps` list before handing it to the decomposer.
Deep validation (required fields, step types) happens in `ValidatorWrapper`.

---

## LLM Mode Flow

```
IFU text
  ↓
PromptBuilder.build(ifu_text, context)
  ↓ (prompt string)
LLMClient.generate_tdf(prompt)
  ↓ (TDF dict or StructuredJSONError)
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
tdf = client.generate_tdf(prompt)
print(tdf)  # {"steps": [...]}
```
