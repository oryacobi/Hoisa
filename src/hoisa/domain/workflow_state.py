"""Workflow state vocabulary shared by Hoisa domain records."""

from enum import StrEnum

from pydantic import Field

from hoisa.domain.models import HoisaModel, UtcDatetime


class WorkflowStage(StrEnum):
    """Workflow stages tracked by Hoisa."""

    PLANNING = "Planning"
    PLAN_REVIEW = "Plan Review"
    PLAN_APPROVAL = "Plan Approval"
    IMPLEMENTATION = "Implementation"
    IMPLEMENTATION_REVIEW = "Implementation Review"
    IMPLEMENTED = "Implemented"


class QueueStatus(StrEnum):
    """Queue ownership status for a work item."""

    TODO = "Todo"
    IN_PROGRESS = "In Progress"
    DONE = "Done"
    BLOCKED = "Blocked"


class ReviewRoute(StrEnum):
    """Independent review route for plans and implementations."""

    HUMAN_ONLY = "Human Only"
    REVIEW_PLAN = "Review Plan"
    REVIEW_IMPLEMENTATION = "Review Implementation"
    REVIEW_BOTH = "Review Both"


class RiskLevel(StrEnum):
    """Workflow risk classification."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class WorkItemType(StrEnum):
    """High-level tracker issue type."""

    TASK = "task"
    SPIKE = "spike"


class Lease(HoisaModel):
    """Worker lease for an in-progress item."""

    worker_id: str = Field(min_length=1)
    claimed_at: UtcDatetime
    expires_at: UtcDatetime


class Blocker(HoisaModel):
    """Reason a workflow item cannot currently advance."""

    blocker_id: str = Field(min_length=1)
    summary: str = Field(min_length=1)
    created_at: UtcDatetime
    resolved_at: UtcDatetime | None = None


class WorkflowState(HoisaModel):
    """Current lifecycle and queue state for a work item."""

    stage: WorkflowStage
    status: QueueStatus
    review_route: ReviewRoute
    risk: RiskLevel
    lease: Lease | None = None
    blockers: tuple[Blocker, ...] = ()
