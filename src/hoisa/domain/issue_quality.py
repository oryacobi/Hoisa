"""Public-safe issue quality, risk, and trust records."""

from dataclasses import dataclass
from typing import Literal

from hoisa.domain.workflow_vocabulary import RiskLevel

IssueQualitySeverity = Literal["info", "warning", "blocking"]


@dataclass(frozen=True, slots=True)
class IssueQualityInput:
    """Fixture-shaped issue facts needed by the issue-quality evaluator."""

    number: int
    title: str
    labels: tuple[str, ...] = ()
    body: str = ""
    author_association: str = ""


@dataclass(frozen=True, slots=True)
class IssueQualityComment:
    """Fixture-shaped comment facts used for trust-boundary checks."""

    body: str
    author_association: str = ""
    source: str = ""


@dataclass(frozen=True, slots=True)
class IssueQualityFinding:
    """A stable issue-quality finding for humans and automation."""

    code: str
    severity: IssueQualitySeverity
    message: str
    source: str = ""


@dataclass(frozen=True, slots=True)
class IssueQualityReport:
    """Read-only readiness, risk, and trust report for an issue."""

    issue: int
    title: str
    issue_type: str
    risk_level: RiskLevel
    risk_reasons: tuple[str, ...]
    ready_for_planning: bool
    ready_for_implementation: bool
    missing_sections: tuple[str, ...]
    findings: tuple[IssueQualityFinding, ...]
    trust_warnings: tuple[IssueQualityFinding, ...]
    recommended_next_action: str
