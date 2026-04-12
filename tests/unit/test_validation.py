import pytest
from execution_engine.models.workflow import Step, Workflow
from execution_engine.validation.validator_wrapper import ValidatorWrapper
from execution_engine.validation.feedback_builder import FeedbackBuilder
from execution_engine.models.feedback import ValidationFeedback, FeedbackItem
from execution_engine.capability_registry.loader import load_default_registry


@pytest.fixture
def registry():
    return load_default_registry()


@pytest.fixture
def validator(registry):
    return ValidatorWrapper(registry=registry)


@pytest.fixture
def validator_no_registry():
    return ValidatorWrapper(registry=None)


class TestSchemaValidation:
    def test_unknown_step_type_is_an_error(self, validator):
        step = Step(type="fly_to_moon", params={})
        feedback = validator.validate_workflow(Workflow(steps=[step]))
        assert not feedback.is_valid
        assert any(e.type == "unknown_step_type" for e in feedback.errors)

    def test_missing_required_field_is_an_error(self, validator):
        # reagent_distribution requires labware_target
        step = Step(type="reagent_distribution", params={
            "volumes": [100],
            "labware_source": "Reagent_Trough_100mL",
            # labware_target missing
        })
        feedback = validator.validate_workflow(Workflow(steps=[step]))
        assert not feedback.is_valid
        assert any(e.type == "missing_required_field" for e in feedback.errors)

    def test_missing_get_tips_tip_type(self, validator):
        step = Step(type="get_tips", params={})
        feedback = validator.validate_workflow(Workflow(steps=[step]))
        assert not feedback.is_valid
        assert any(e.type == "missing_required_field" for e in feedback.errors)

    def test_valid_full_distribution_step(self, validator):
        step = Step(type="reagent_distribution", params={
            "volumes": [100],
            "labware_source": "Reagent_Trough_100mL",
            "labware_target": "Plate_96_Well",
            "tip_type": "DiTi_200uL",
            "liquid_class": "Buffer",
        })
        feedback = validator.validate_workflow(Workflow(steps=[step]))
        assert feedback.is_valid

    def test_empty_tips_has_no_required_fields(self, validator):
        step = Step(type="empty_tips", params={})
        feedback = validator.validate_workflow(Workflow(steps=[step]))
        assert feedback.is_valid


class TestSemanticValidation:
    def test_unknown_tip_type(self, validator):
        step = Step(type="reagent_distribution", params={
            "volumes": [100],
            "labware_source": "Reagent_Trough_100mL",
            "labware_target": "Plate_96_Well",
            "tip_type": "DiTi_SuperGiant",
        })
        feedback = validator.validate_step(step)
        assert any(e.type == "unknown_tip_type" for e in feedback.errors)

    def test_unknown_liquid_class(self, validator):
        step = Step(type="reagent_distribution", params={
            "volumes": [100],
            "labware_source": "Reagent_Trough_100mL",
            "labware_target": "Plate_96_Well",
            "liquid_class": "MagicSolvent",
        })
        feedback = validator.validate_step(step)
        assert any(e.type == "unknown_liquid_class" for e in feedback.errors)

    def test_tip_volume_out_of_range(self, validator):
        # DiTi_10uL max is 10 µL; volume 500 µL is out of range
        step = Step(type="reagent_distribution", params={
            "volumes": [500],
            "labware_source": "Reagent_Trough_100mL",
            "labware_target": "Plate_96_Well",
            "tip_type": "DiTi_10uL",
        })
        feedback = validator.validate_step(step)
        assert any(e.type == "tip_volume_out_of_range" for e in feedback.errors)

    def test_liquid_tip_incompatible(self, validator):
        # DiTi_10uL only supports [Water, Buffer]; Serum is not in its list
        step = Step(type="reagent_distribution", params={
            "volumes": [5],
            "labware_source": "Reagent_Trough_100mL",
            "labware_target": "Plate_96_Well",
            "tip_type": "DiTi_10uL",
            "liquid_class": "Serum",
        })
        feedback = validator.validate_step(step)
        assert any(e.type == "liquid_tip_incompatible" for e in feedback.errors)

    def test_diti_type_alias_recognized(self, validator):
        # DiTi_type alias should be treated the same as tip_type
        step = Step(type="reagent_distribution", params={
            "volumes": [100],
            "labware_source": "Reagent_Trough_100mL",
            "labware_target": "Plate_96_Well",
            "DiTi_type": "DiTi_200uL",
            "liquid_class": "Buffer",
        })
        feedback = validator.validate_step(step)
        assert not any(e.type == "unknown_tip_type" for e in feedback.errors)

    def test_diti_type_lowercase_alias_recognized(self, validator):
        step = Step(type="reagent_distribution", params={
            "volumes": [100],
            "labware_source": "Reagent_Trough_100mL",
            "labware_target": "Plate_96_Well",
            "diti_type": "DiTi_200uL",
            "liquid_class": "Buffer",
        })
        feedback = validator.validate_step(step)
        assert not any(e.type == "unknown_tip_type" for e in feedback.errors)

    def test_warning_for_unspecified_tip(self, validator):
        step = Step(type="reagent_distribution", params={
            "volumes": [100],
            "labware_source": "Reagent_Trough_100mL",
            "labware_target": "Plate_96_Well",
        })
        feedback = validator.validate_step(step)
        assert any(w.type == "unspecified_tip_type" for w in feedback.warnings)

    def test_warning_for_unspecified_liquid_class(self, validator):
        step = Step(type="reagent_distribution", params={
            "volumes": [100],
            "labware_source": "Reagent_Trough_100mL",
            "labware_target": "Plate_96_Well",
        })
        feedback = validator.validate_step(step)
        assert any(w.type == "unspecified_liquid_class" for w in feedback.warnings)

    def test_no_semantic_errors_without_registry(self, validator_no_registry):
        # Semantic checks are skipped when no registry is provided
        step = Step(type="reagent_distribution", params={
            "volumes": [100],
            "labware_source": "Reagent_Trough_100mL",
            "labware_target": "Plate_96_Well",
            "tip_type": "DiTi_SuperGiant",
        })
        feedback = validator_no_registry.validate_step(step)
        assert not any(e.type == "unknown_tip_type" for e in feedback.errors)


class TestFeedbackBuilder:
    def test_summarize_valid(self):
        fb = ValidationFeedback()
        builder = FeedbackBuilder()
        summary = builder.summarize(fb)
        assert "Valid" in summary

    def test_summarize_invalid(self):
        fb = ValidationFeedback(errors=[FeedbackItem(type="missing_required_field", message="x")])
        builder = FeedbackBuilder()
        summary = builder.summarize(fb)
        assert "Invalid" in summary

    def test_retry_prompt_contains_error_info(self):
        fb = ValidationFeedback(errors=[
            FeedbackItem(
                type="missing_required_field",
                message="Step missing 'volumes'",
                context="step[0]",
            )
        ])
        builder = FeedbackBuilder()
        prompt = builder.build_retry_prompt(fb, "Original prompt text")
        assert "missing_required_field" in prompt.lower() or "Missing Required" in prompt
        assert "Original prompt text" in prompt
