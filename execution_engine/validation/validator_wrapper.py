from typing import Any, Dict, List, Optional

from ..models.workflow import Step, Workflow, STEP_SCHEMA
from ..models.feedback import FeedbackItem, ValidationFeedback
from ..capability_registry.registry import CapabilityRegistry

# All field name aliases for tip type across IR dialects
TIP_TYPE_ALIASES = ["tip_type", "DiTi_type", "diti_type"]

# All field names that identify a labware item in step params
LABWARE_FIELDS = [
    "labware", "labware_source", "labware_target",
    "labware_empty_tips", "labware_name", "source", "target",
]

# Step types where unspecified tip should produce warnings
_TIP_RELEVANT_TYPES = {
    "reagent_distribution", "sample_transfer",
    "get_tips",
}

# Step types where unspecified liquid class should produce warnings
_LIQUID_RELEVANT_TYPES = {
    "reagent_distribution", "sample_transfer",
    "aspirate_volume", "dispense_volume", "mix_volume",
}


def _get_tip_type(params: Dict[str, Any]) -> Optional[str]:
    """Resolve tip type from any accepted alias."""
    for alias in TIP_TYPE_ALIASES:
        if alias in params:
            return params[alias]
    return None


def _get_labware_names(params: Dict[str, Any]) -> List[str]:
    """Extract all non-None labware values from a step's params."""
    return [params[f] for f in LABWARE_FIELDS if params.get(f)]


class ValidatorWrapper:
    """Two-layer validator: schema validation then semantic validation.

    Layer 1 — validate_workflow():
        Structural checks driven by STEP_SCHEMA.
        Detects unknown step types and missing required fields.

    Layer 2 — validate_step():
        Semantic checks using registry knowledge.
        Does NOT re-check required fields (that is Layer 1's job).

    Registry is optional — semantic checks are skipped when not provided.
    """

    def __init__(self, registry: Optional[CapabilityRegistry] = None):
        self.registry = registry

    def validate_workflow(self, workflow: Workflow) -> ValidationFeedback:
        """Validate all steps in a workflow. Returns aggregated feedback."""
        feedback = ValidationFeedback()

        for idx, step in enumerate(workflow.steps):
            step_label = step.id or f"step[{idx}]"

            # --- Layer 1: Schema validation ---
            if step.type not in STEP_SCHEMA:
                feedback.errors.append(FeedbackItem(
                    type="unknown_step_type",
                    message=f"Unknown step type '{step.type}'.",
                    suggestion=f"Use one of: {', '.join(sorted(STEP_SCHEMA.keys()))}",
                    context=step_label,
                    severity="error",
                ))
                continue  # Cannot check required fields for an unknown type

            schema = STEP_SCHEMA[step.type]
            for req_field in schema.get("required", []):
                if req_field not in step.params:
                    feedback.errors.append(FeedbackItem(
                        type="missing_required_field",
                        message=f"Step '{step.type}' is missing required field '{req_field}'.",
                        suggestion=f"Add '{req_field}' to the step params.",
                        context=step_label,
                        severity="error",
                    ))

            # --- Layer 2: Semantic validation ---
            step_feedback = self.validate_step(step)
            feedback.errors.extend(step_feedback.errors)
            feedback.warnings.extend(step_feedback.warnings)

        return feedback

    def validate_step(self, step: Step) -> ValidationFeedback:
        """Semantic validation for a single step.

        Does NOT re-check required fields — that belongs in validate_workflow.
        """
        feedback = ValidationFeedback()
        params = step.params

        tip_name = _get_tip_type(params)
        liquid_name = params.get("liquid_class")
        volumes = params.get("volumes") or params.get("volume_uL")

        # Unknown tip type
        if tip_name and self.registry:
            tip = self.registry.get_tip(tip_name)
            if tip is None:
                feedback.errors.append(FeedbackItem(
                    type="unknown_tip_type",
                    message=f"Tip type '{tip_name}' is not in the registry.",
                    suggestion="Check registry.yaml for available tip types.",
                    context=step.id,
                    severity="error",
                ))
            else:
                # Volume vs tip range check
                check_vol: Optional[float] = None
                if isinstance(volumes, (int, float)):
                    check_vol = float(volumes)
                elif isinstance(volumes, list) and volumes:
                    check_vol = float(max(volumes))

                if check_vol is not None:
                    if check_vol < tip.min_volume_uL or check_vol > tip.max_volume_uL:
                        feedback.errors.append(FeedbackItem(
                            type="tip_volume_out_of_range",
                            message=(
                                f"Volume {check_vol} µL is outside tip '{tip_name}' "
                                f"range [{tip.min_volume_uL}, {tip.max_volume_uL}] µL."
                            ),
                            suggestion="Select a tip whose volume range covers the specified volume.",
                            context=step.id,
                            severity="error",
                        ))

        # Unknown liquid class
        if liquid_name and self.registry:
            lc = self.registry.get_liquid_class(liquid_name)
            if lc is None:
                feedback.errors.append(FeedbackItem(
                    type="unknown_liquid_class",
                    message=f"Liquid class '{liquid_name}' is not in the registry.",
                    suggestion="Check registry.yaml for available liquid classes.",
                    context=step.id,
                    severity="error",
                ))

        # Liquid / tip compatibility
        if tip_name and liquid_name and self.registry:
            if not self.registry.tip_compatible_with_liquid(tip_name, liquid_name):
                feedback.errors.append(FeedbackItem(
                    type="liquid_tip_incompatible",
                    message=f"Tip '{tip_name}' is not compatible with liquid class '{liquid_name}'.",
                    suggestion="Choose a compatible tip/liquid combination from the registry.",
                    context=step.id,
                    severity="error",
                ))

        # Warn on unspecified tip type for liquid-handling steps
        if step.type in _TIP_RELEVANT_TYPES and not tip_name:
            feedback.warnings.append(FeedbackItem(
                type="unspecified_tip_type",
                message=f"Step '{step.type}' has no tip_type specified.",
                suggestion="Specify a tip_type for precise tip selection.",
                context=step.id,
                severity="warning",
            ))
        
        # Warn on unspecified liquid class for liquid-handling steps
        if step.type in _LIQUID_RELEVANT_TYPES and not liquid_name:
            feedback.warnings.append(FeedbackItem(
                type="unspecified_liquid_class",
                message=f"Step '{step.type}' has no liquid_class specified.",
                suggestion="Specify a liquid_class for accurate dispensing behavior.",
                context=step.id,
                severity="warning",
            ))       

        # Labware existence check (warning only — labware may be runtime-defined)
        if self.registry:
            for lw_name in _get_labware_names(params):
                if self.registry.get_labware(lw_name) is None:
                    feedback.warnings.append(FeedbackItem(
                        type="unknown_labware",
                        message=f"Labware '{lw_name}' is not in the registry.",
                        suggestion="Verify the labware name against registry.yaml.",
                        context=step.id,
                        severity="warning",
                    ))

        return feedback
