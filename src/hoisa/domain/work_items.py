"""Work item domain vocabulary shared by application workflows and ports."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class WorkflowStage(StrEnum):
    """Workflow stages that can own runnable Hoisa work."""

    PLANNING = "Planning"
    PLAN_REVIEW = "Plan Review"
    IMPLEMENTATION = "Implementation"
    IMPLEMENTATION_REVIEW = "Implementation Review"


@dataclass(frozen=True, slots=True)
class WorkItemRef:
    """Tracker-independent reference to a Hoisa work item."""

    value: str
