import pytest
from execution_engine.models.workflow import Step
from execution_engine.models.plan import Plan
from execution_engine.planner.candidate_selector import CandidateSelector
from execution_engine.planner.scoring import ScoringEngine
from execution_engine.planner.variable_mapper import VariableMapper
from execution_engine.planner.planner import Planner, PlannerError
from execution_engine.capability_registry.loader import load_default_registry


@pytest.fixture
def registry():
    return load_default_registry()


@pytest.fixture
def selector(registry):
    return CandidateSelector(registry)


@pytest.fixture
def scorer(registry):
    return ScoringEngine(registry)


@pytest.fixture
def planner(registry):
    return Planner(registry, enable_liquid_inference=True)


class TestCandidateSelector:
    def test_reagent_distribution_returns_candidates(self, selector):
        step = Step(type="reagent_distribution", params={
            "volumes": [100],
            "labware_source": "Reagent_Trough_100mL",
            "labware_target": "Plate_96_Well",
        })
        candidates = selector.select(step)
        assert len(candidates) > 0
        assert any(c.name == "ReagentDistribution" for c in candidates)

    def test_unknown_step_type_returns_empty(self, selector):
        step = Step(type="impossible_step", params={})
        assert selector.select(step) == []

    def test_get_tips_returns_get_tips_method(self, selector):
        step = Step(type="get_tips", params={"tip_type": "DiTi_200uL"})
        candidates = selector.select(step)
        assert any(c.name == "GetTips" for c in candidates)

    def test_incubate_returns_incubate_method(self, selector):
        step = Step(type="incubate", params={"duration_seconds": 600})
        candidates = selector.select(step)
        assert any(c.name == "Incubate" for c in candidates)

    def test_incompatible_tip_filters_method(self, selector):
        # DiTi_10uL is not in ReagentDistribution.tip_types
        step = Step(type="reagent_distribution", params={
            "volumes": [5],
            "labware_source": "Reagent_Trough_100mL",
            "labware_target": "Plate_96_Well",
            "tip_type": "DiTi_10uL",
        })
        candidates = selector.select(step)
        # ReagentDistribution should be filtered out; only methods supporting DiTi_10uL remain
        names = [c.name for c in candidates]
        assert "ReagentDistribution" not in names

    def test_volume_out_of_range_filters_method(self, selector):
        # MixVolume max is 200 µL; 5000 µL should filter it out
        step = Step(type="mix_volume", params={"volumes": [5000], "labware": "Plate_96_Well"})
        candidates = selector.select(step)
        assert not any(c.name == "MixVolume" for c in candidates)


class TestScoringEngine:
    def test_returns_float_score_and_string_reasoning(self, scorer, registry):
        method = registry.get_method("ReagentDistribution")
        step = Step(type="reagent_distribution", params={
            "volumes": [100],
            "tip_type": "DiTi_200uL",
            "liquid_class": "Buffer",
        })
        score, reasoning = scorer.score(step, method)
        assert isinstance(score, float)
        assert isinstance(reasoning, str)
        assert 0.0 <= score <= 1.0

    def test_matched_tip_and_liquid_scores_higher_than_unspecified(self, scorer, registry):
        method = registry.get_method("ReagentDistribution")
        step_full = Step(type="reagent_distribution", params={
            "volumes": [100], "tip_type": "DiTi_200uL", "liquid_class": "Buffer",
        })
        step_bare = Step(type="reagent_distribution", params={"volumes": [100]})
        score_full, _ = scorer.score(step_full, method)
        score_bare, _ = scorer.score(step_bare, method)
        assert score_full >= score_bare

    def test_reasoning_is_non_empty(self, scorer, registry):
        method = registry.get_method("Incubate")
        step = Step(type="incubate", params={"duration_seconds": 600})
        _, reasoning = scorer.score(step, method)
        assert len(reasoning) > 0


class TestVariableMapper:
    def setup_method(self):
        self.mapper = VariableMapper()

    def test_distribution_maps_tip_alias(self):
        step = Step(type="reagent_distribution", params={
            "volumes": [100],
            "DiTi_type": "DiTi_200uL",
            "liquid_class": "Buffer",
            "labware_source": "Reagent_Trough_100mL",
            "labware_target": "Plate_96_Well",
        })
        variables = self.mapper.map(step, "ReagentDistribution")
        assert variables["tip_type"] == "DiTi_200uL"
        assert variables["labware_source"] == "Reagent_Trough_100mL"

    def test_mix_volume_includes_cycles(self):
        step = Step(type="mix_volume", params={
            "volumes": [80], "labware": "Plate_96_Well", "cycles": 5,
        })
        variables = self.mapper.map(step, "MixVolume")
        assert variables["cycles"] == 5

    def test_mix_volume_without_cycles_omits_key(self):
        step = Step(type="mix_volume", params={"volumes": [80], "labware": "Plate_96_Well"})
        variables = self.mapper.map(step, "MixVolume")
        assert "cycles" not in variables

    def test_transfer_labware_mapping(self):
        step = Step(type="transfer_labware", params={
            "labware_name": "Plate_96_Well",
            "target_location": "Slot_3",
            "target_position": 1,
        })
        variables = self.mapper.map(step, "TransferLabware")
        assert variables["labware_name"] == "Plate_96_Well"
        assert variables["target_location"] == "Slot_3"
        assert variables["target_position"] == 1

    def test_get_tips_normalizes_diti_type(self):
        step = Step(type="get_tips", params={"diti_type": "DiTi_1000uL"})
        variables = self.mapper.map(step, "GetTips")
        assert variables["tip_type"] == "DiTi_1000uL"

    def test_incubate_maps_all_fields(self):
        step = Step(type="incubate", params={
            "duration_seconds": 3600,
            "temperature_celsius": 37.0,
            "device": "Heated_Incubator",
        })
        variables = self.mapper.map(step, "Incubate")
        assert variables["duration_seconds"] == 3600
        assert variables["temperature_celsius"] == 37.0
        assert variables["device"] == "Heated_Incubator"

    def test_none_values_are_not_included(self):
        step = Step(type="incubate", params={
            "duration_seconds": 600,
            "temperature_celsius": None,
        })
        variables = self.mapper.map(step, "Incubate")
        assert "temperature_celsius" not in variables

    def test_well_offset_alias_normalized(self):
        step = Step(type="aspirate_volume", params={
            "volumes": [50], "labware": "Plate_96_Well", "well_offset": "A1",
        })
        variables = self.mapper.map(step, "AspirateVolume")
        assert variables.get("well_offsets") == "A1"


class TestPlanner:
    def test_plan_reagent_distribution_returns_plan(self, planner):
        step = Step(type="reagent_distribution", params={
            "volumes": [100],
            "labware_source": "Reagent_Trough_100mL",
            "labware_target": "Plate_96_Well",
            "tip_type": "DiTi_200uL",
            "liquid_class": "Buffer",
        })
        plan = planner.plan(step)
        assert isinstance(plan, Plan)
        assert plan.method_name == "ReagentDistribution"
        assert plan.score > 0

    def test_plan_incubate(self, planner):
        step = Step(type="incubate", params={"duration_seconds": 1800, "temperature_celsius": 37})
        plan = planner.plan(step)
        assert plan.method_name == "Incubate"

    def test_plan_raises_for_unknown_step(self, planner):
        step = Step(type="teleport_sample", params={})
        with pytest.raises(PlannerError):
            planner.plan(step)

    def test_plan_workflow_plans_all_steps(self, planner):
        steps = [
            Step(type="get_tips", params={"tip_type": "DiTi_200uL"}),
            Step(type="reagent_distribution", params={
                "volumes": [100],
                "labware_source": "Reagent_Trough_100mL",
                "labware_target": "Plate_96_Well",
            }),
            Step(type="drop_tips_to_location", params={"labware": "Waste_Container"}),
        ]
        plans = planner.plan_workflow(steps)
        assert len(plans) == 3
