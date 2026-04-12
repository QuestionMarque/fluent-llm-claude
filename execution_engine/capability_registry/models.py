from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass(frozen=True)
class MetaFlags:
    """Provenance metadata for registry entries."""
    documented: bool = True
    inferred: bool = False
    unknown: bool = False


@dataclass(frozen=True)
class Device:
    """A physical instrument on the Fluent worktable."""
    name: str
    type: str
    capabilities: List[str] = field(default_factory=list)
    channels: Optional[int] = None
    constraints: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class TipType:
    """A disposable tip type with volume limits."""
    name: str
    min_volume_uL: float
    max_volume_uL: float
    filter: bool = False
    purity_level: str = "standard"
    meta: MetaFlags = field(default_factory=MetaFlags)


@dataclass(frozen=True)
class LiquidClass:
    """A liquid class defining dispensing behavior."""
    name: str
    dispense_mode: str = "standard"
    compatible_tips: List[str] = field(default_factory=list)
    meta: MetaFlags = field(default_factory=MetaFlags)


@dataclass(frozen=True)
class Labware:
    """A labware item that can be placed on the worktable."""
    name: str
    format: str = "SBS"
    wells: int = 96
    max_volume_uL: float = 200.0
    geometry: str = "flat"
    meta: MetaFlags = field(default_factory=MetaFlags)


@dataclass(frozen=True)
class Operation:
    """A single atomic operation supported by the system."""
    name: str
    step_type: str
    description: str = ""


@dataclass(frozen=True)
class Method:
    """A FluentControl method that maps to one or more step types."""
    name: str
    supports: List[str] = field(default_factory=list)      # step types this method handles
    tip_types: List[str] = field(default_factory=list)
    liquid_classes: List[str] = field(default_factory=list)
    min_volume_uL: float = 0.0
    max_volume_uL: float = 1000.0
    variables: List[str] = field(default_factory=list)     # expected runtime variable names
    description: str = ""


@dataclass(frozen=True)
class Rule:
    """A named constraint or preference rule."""
    name: str
    condition: str
    action: str
    severity: str = "warning"


@dataclass
class ValidationIssue:
    """A single issue found during registry self-validation."""
    severity: str   # "error" | "warning"
    message: str
    context: Optional[str] = None


@dataclass
class ValidationResult:
    """Aggregated result of a registry self-validation pass."""
    issues: List[ValidationIssue] = field(default_factory=list)

    @property
    def is_valid(self) -> bool:
        return not any(i.severity == "error" for i in self.issues)

    @property
    def errors(self) -> List[ValidationIssue]:
        return [i for i in self.issues if i.severity == "error"]

    @property
    def warnings(self) -> List[ValidationIssue]:
        return [i for i in self.issues if i.severity == "warning"]
