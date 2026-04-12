from typing import Tuple
from ..models.feedback import ValidationFeedback

# Maps error type -> (human label, corrective guidance)
ERROR_TAXONOMY = {
    "unknown_step_type": (
        "Unknown Step Type",
        "Use one of the supported step types defined in STEP_SCHEMA.",
    ),
    "missing_required_field": (
        "Missing Required Field",
        "Ensure all required fields for the step type are present.",
    ),
    "unknown_tip_type": (
        "Unknown Tip Type",
        "Check the tip types listed in the capability registry (registry.yaml).",
    ),
    "unknown_liquid_class": (
        "Unknown Liquid Class",
        "Check the liquid classes listed in the capability registry (registry.yaml).",
    ),
    "tip_volume_out_of_range": (
        "Tip Volume Out of Range",
        "Select a tip whose volume range covers the specified volume.",
    ),
    "liquid_tip_incompatible": (
        "Liquid/Tip Incompatibility",
        "Use a tip type that is compatible with the specified liquid class.",
    ),
    "unknown_labware": (
        "Unknown Labware",
        "Verify the labware name against the capability registry.",
    ),
    "unspecified_tip_type": (
        "Unspecified Tip Type",
        "Provide a tip_type to enable precise tip selection.",
    ),
    "unspecified_liquid_class": (
        "Unspecified Liquid Class",
        "Provide a liquid_class for accurate dispensing behavior.",
    ),
}


class FeedbackBuilder:
    """Converts ValidationFeedback into structured output and LLM retry prompts."""

    def build_retry_prompt(self, feedback: ValidationFeedback, original_prompt: str) -> str:
        """Build an LLM prompt that instructs the model to correct its TDF output."""
        lines = [
            "The previous TDF output failed validation. Please correct the errors "
            "listed below and re-generate a valid TDF JSON.",
            "",
            "=== ERRORS ===",
        ]
        for item in feedback.errors:
            label, guidance = ERROR_TAXONOMY.get(item.type, (item.type, ""))
            ctx = f" (context: {item.context})" if item.context else ""
            lines.append(f"- [{label}]{ctx}: {item.message}")
            if guidance:
                lines.append(f"  Guidance: {guidance}")
            if item.suggestion:
                lines.append(f"  Suggestion: {item.suggestion}")

        if feedback.warnings:
            lines += ["", "=== WARNINGS (advisory) ==="]
            for item in feedback.warnings:
                label, _ = ERROR_TAXONOMY.get(item.type, (item.type, ""))
                lines.append(f"- [{label}]: {item.message}")

        lines += [
            "",
            "=== ORIGINAL PROMPT ===",
            original_prompt,
        ]
        return "\n".join(lines)

    def summarize(self, feedback: ValidationFeedback) -> str:
        """Return a brief human-readable summary of the validation result."""
        n_err = len(feedback.errors)
        n_warn = len(feedback.warnings)
        if feedback.is_valid:
            return f"Valid ({n_warn} warning(s))."
        return f"Invalid: {n_err} error(s), {n_warn} warning(s)."
