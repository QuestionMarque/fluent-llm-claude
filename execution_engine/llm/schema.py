"""JSON schema for validating LLM-generated IR output.

Used to catch structural issues before passing IR to the decomposer.
Deep validation (required fields, step types) happens in ValidatorWrapper.
"""

IR_SCHEMA = {
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
