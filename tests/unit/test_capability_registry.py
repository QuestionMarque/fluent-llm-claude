import pytest

from execution_engine.capability_registry.loader import (
    RegistryLoadError,
    load_default_registry,
)
from execution_engine.capability_registry.models import Method
from execution_engine.capability_registry.registry import CapabilityRegistry
from execution_engine.capability_registry.validator import RegistryValidator
from execution_engine.models.workflow import STEP_SCHEMA


class TestDefaultRegistryLoads:
    def test_default_registry_passes_validation(self):
        """The bundled registry.yaml must satisfy every load-time invariant."""
        registry = load_default_registry()
        assert isinstance(registry, CapabilityRegistry)
        assert len(registry.methods) > 0


class TestRegistryValidatorInvariants:
    def _make_registry(self, methods):
        registry = CapabilityRegistry()
        for m in methods:
            registry.methods[m.name] = m
        return registry

    def test_one_method_per_step_type_passes(self):
        registry = self._make_registry([
            Method(name="ReagentDistribution", supports=["reagent_distribution"]),
            Method(name="GetTips", supports=["get_tips"]),
        ])
        result = RegistryValidator().validate(
            registry,
            expected_step_types=["reagent_distribution", "get_tips"],
        )
        assert result.is_valid

    def test_duplicate_step_type_is_error(self):
        registry = self._make_registry([
            Method(name="MethodA", supports=["reagent_distribution"]),
            Method(name="MethodB", supports=["reagent_distribution"]),
        ])
        result = RegistryValidator().validate(
            registry,
            expected_step_types=["reagent_distribution"],
        )
        assert not result.is_valid
        msg = result.errors[0].message
        assert "reagent_distribution" in msg
        assert "MethodA" in msg and "MethodB" in msg

    def test_missing_step_type_coverage_is_error(self):
        registry = self._make_registry([
            Method(name="GetTips", supports=["get_tips"]),
        ])
        result = RegistryValidator().validate(
            registry,
            expected_step_types=["get_tips", "reagent_distribution"],
        )
        assert not result.is_valid
        assert any(
            "reagent_distribution" in e.message for e in result.errors
        )

    def test_default_step_types_use_step_schema(self):
        """Without expected_step_types, validator falls back to STEP_SCHEMA keys."""
        registry = self._make_registry([
            Method(name="GetTips", supports=["get_tips"]),
        ])
        result = RegistryValidator().validate(registry)
        assert not result.is_valid
        # Every other STEP_SCHEMA entry should produce a coverage error.
        missing = {e.context for e in result.errors}
        for step_type in STEP_SCHEMA.keys():
            if step_type != "get_tips":
                assert step_type in missing


class TestLoaderFailsFastOnBrokenRegistry:
    def test_load_registry_raises_on_invariant_violation(self, tmp_path):
        # A registry covering only one step type (so all others are missing).
        bad_yaml = tmp_path / "broken.yaml"
        bad_yaml.write_text(
            "methods:\n"
            "  GetTips:\n"
            "    supports: [get_tips]\n"
            "    tip_types: []\n"
            "    liquid_classes: []\n"
        )
        from execution_engine.capability_registry.loader import load_registry
        with pytest.raises(RegistryLoadError) as exc:
            load_registry(str(bad_yaml))
        assert "reagent_distribution" in str(exc.value)

    def test_load_registry_can_skip_validation(self, tmp_path):
        bad_yaml = tmp_path / "broken.yaml"
        bad_yaml.write_text(
            "methods:\n"
            "  GetTips:\n"
            "    supports: [get_tips]\n"
            "    tip_types: []\n"
            "    liquid_classes: []\n"
        )
        from execution_engine.capability_registry.loader import load_registry
        # validate=False bypasses the invariant — only useful in tests.
        registry = load_registry(str(bad_yaml), validate=False)
        assert "GetTips" in registry.methods
