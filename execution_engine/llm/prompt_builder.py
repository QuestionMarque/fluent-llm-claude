from typing import Optional

from ..capability_registry.registry import CapabilityRegistry
from ..models.workflow import STEP_SCHEMA


class PromptBuilder:
    """Builds prompts for LLM-driven IFU → IR generation.

    Injects capability context (step types, tips, liquids, labware)
    so the LLM can generate schema-valid IR without hallucinating
    registry entries that don't exist.
    """

    SYSTEM_PROMPT = (
        "You are a lab automation expert. Convert the user's lab protocol "
        "(IFU — Instructions for Use) into a structured IR (Intermediate Representation) "
        "JSON object.\n\n"
        "Rules:\n"
        "- Output must be valid JSON with a top-level 'steps' list.\n"
        "- Each step must have a 'type' field matching a supported step type.\n"
        "- Include all required fields for each step type.\n"
        "- Do not include markdown fences, explanations, or extra keys outside the JSON.\n"
        "- If you make assumptions, document them in a top-level 'assumptions' list.\n"
        "- Prefer specific parameter values over vague placeholders.\n"
    )

    def __init__(self, registry: Optional[CapabilityRegistry] = None):
        self.registry = registry

    def build(self, ifu_text: str, context: Optional[str] = None) -> str:
        """Build a complete prompt string for IR generation."""
        parts = [self.SYSTEM_PROMPT]

        parts.append("\n=== SUPPORTED STEP TYPES ===")
        for step_type, schema in STEP_SCHEMA.items():
            req = ", ".join(schema.get("required", [])) or "none"
            opt = ", ".join(schema.get("optional", [])) or "none"
            parts.append(f"- {step_type}")
            parts.append(f"    required: [{req}]")
            parts.append(f"    optional: [{opt}]")

        if self.registry:
            parts.append("\n=== AVAILABLE TIP TYPES ===")
            for name, tip in self.registry.tips.items():
                parts.append(
                    f"- {name} ({tip.min_volume_uL}–{tip.max_volume_uL} µL"
                    + (", filter" if tip.filter else "") + ")"
                )

            parts.append("\n=== AVAILABLE LIQUID CLASSES ===")
            for name in self.registry.liquid_classes:
                parts.append(f"- {name}")

            parts.append("\n=== AVAILABLE LABWARE ===")
            for name in self.registry.labware:
                parts.append(f"- {name}")

        if context:
            parts.append(f"\n=== CONTEXT ===\n{context}")

        parts.append(f"\n=== INSTRUCTION (IFU) ===\n{ifu_text}")
        parts.append("\nRespond with a valid IR JSON object only.")
        return "\n".join(parts)
