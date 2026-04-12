"""JSON schema for validating LLM-generated TDF output.

Used to catch structural issues before passing TDF to the decomposer.
Deep validation (required fields, step types) happens in ValidatorWrapper.
"""

TDF_SCHEMA = {
    "type": "object",
    "required": ["steps"],
    "properties": {
        "name": {"type": "string"},
        "description": {"type": "string"},
        "assumptions": {
            "type": "array",
            "items": {"type": "string"},
        },
        "steps": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["type"],
                "properties": {
                    "type": {"type": "string"},
                    "id": {"type": "string"},
                },
                "additionalProperties": True,
            },
        },
    },
}
