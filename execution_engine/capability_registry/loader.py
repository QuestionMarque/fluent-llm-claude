import os
from typing import Any, Dict

import yaml

from .models import Device, MetaFlags, TipType, LiquidClass, Labware, Method, Rule
from .registry import CapabilityRegistry

_DEFAULT_REGISTRY_PATH = os.path.join(
    os.path.dirname(__file__), "data", "registry.yaml"
)


def load_default_registry() -> CapabilityRegistry:
    """Load the bundled registry.yaml shipped with the package."""
    return load_registry(_DEFAULT_REGISTRY_PATH)


def load_registry(path: str) -> CapabilityRegistry:
    """Load a CapabilityRegistry from a YAML file at the given path."""
    with open(path, "r") as f:
        data = yaml.safe_load(f)
    return _build_registry(data)


def _build_registry(data: Dict[str, Any]) -> CapabilityRegistry:
    registry = CapabilityRegistry()

    for name, cfg in data.get("devices", {}).items():
        registry.devices[name] = Device(
            name=name,
            type=cfg.get("type", "unknown"),
            capabilities=cfg.get("capabilities", []),
            channels=cfg.get("channels"),
            constraints=cfg.get("constraints", {}),
        )

    for name, cfg in data.get("tips", {}).items():
        registry.tips[name] = TipType(
            name=name,
            min_volume_uL=float(cfg.get("min_volume_uL", 0)),
            max_volume_uL=float(cfg.get("max_volume_uL", 1000)),
            filter=cfg.get("filter", False),
            purity_level=cfg.get("purity_level", "standard"),
        )

    for name, cfg in data.get("liquid_classes", {}).items():
        registry.liquid_classes[name] = LiquidClass(
            name=name,
            dispense_mode=cfg.get("dispense_mode", "standard"),
            compatible_tips=cfg.get("compatible_tips", []),
        )

    for name, cfg in data.get("labware", {}).items():
        registry.labware[name] = Labware(
            name=name,
            format=cfg.get("format", "SBS"),
            wells=int(cfg.get("wells", 96)),
            max_volume_uL=float(cfg.get("max_volume_uL", 200)),
            geometry=cfg.get("geometry", "flat"),
        )

    for name, cfg in data.get("methods", {}).items():
        registry.methods[name] = Method(
            name=name,
            supports=cfg.get("supports", []),
            tip_types=cfg.get("tip_types", []),
            liquid_classes=cfg.get("liquid_classes", []),
            min_volume_uL=float(cfg.get("min_volume_uL", 0)),
            max_volume_uL=float(cfg.get("max_volume_uL", 1000)),
            variables=cfg.get("variables", []),
            description=cfg.get("description", ""),
        )

    for name, compat in data.get("tip_liquid_compatibility", {}).items():
        registry.tip_liquid_compatibility[name] = compat

    for rule_cfg in data.get("rules", []):
        registry.rules.append(Rule(
            name=rule_cfg.get("name", "unnamed_rule"),
            condition=rule_cfg.get("condition", ""),
            action=rule_cfg.get("action", ""),
            severity=rule_cfg.get("severity", "warning"),
        ))

    return registry
