import json
import os
from typing import Any, Dict, Optional


class LLMClientError(Exception):
    pass


class StructuredJSONError(LLMClientError):
    pass


class LLMClient:
    """Optional LLM integration for IFU → TDF generation.

    The system must work fully without this class (library mode).
    Only instantiate LLMClient when tdf_mode="llm".

    Supports OpenAI. Extend _call_provider() to add other providers.
    """

    def __init__(
        self,
        provider: str = "openai",
        model: str = "gpt-4o-mini",
        api_key: Optional[str] = None,
        max_json_retries: int = 3,
    ):
        self.provider = provider
        self.model = model
        self.api_key = api_key or os.environ.get("OPENAI_API_KEY")
        self.max_json_retries = max_json_retries
        self._client = None

        if provider == "openai":
            self._init_openai()
        else:
            raise LLMClientError(f"Unsupported provider: '{provider}'")

    def _init_openai(self) -> None:
        try:
            import openai
            self._client = openai.OpenAI(api_key=self.api_key)
        except ImportError:
            raise LLMClientError(
                "openai package is not installed. Run: pip install openai"
            )

    def generate_tdf(self, prompt: str) -> Dict[str, Any]:
        """Generate a TDF dict from a natural-language prompt.

        Retries up to max_json_retries times on JSON parse failures.
        Raises StructuredJSONError after exhausting retries.
        """
        last_error: Optional[Exception] = None

        for attempt in range(1, self.max_json_retries + 1):
            try:
                raw = self._call_provider(prompt)
                return self._parse_json(raw)
            except StructuredJSONError as e:
                last_error = e
                print(f"[LLMClient] JSON parse error (attempt {attempt}): {e}")

        raise StructuredJSONError(
            f"Failed to obtain valid JSON after {self.max_json_retries} attempt(s). "
            f"Last error: {last_error}"
        )

    def _call_provider(self, prompt: str) -> str:
        if self.provider == "openai":
            response = self._client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                response_format={"type": "json_object"},
            )
            return response.choices[0].message.content
        raise LLMClientError(f"Provider '{self.provider}' is not implemented.")

    def _parse_json(self, raw: str) -> Dict[str, Any]:
        try:
            return json.loads(raw)
        except json.JSONDecodeError as e:
            raise StructuredJSONError(
                f"Invalid JSON from LLM: {e}\nContent snippet: {raw[:300]}"
            )
