"""Workflow state vocabulary shared by Hoisa domain records."""

from pydantic import Field

from hoisa.domain.models import HoisaModel, UtcDatetime
from hoisa.domain.workflow_vocabulary import (
    QueueStatus,
    ReviewRoute,
    RiskLevel,
    WorkflowStage,
    WorkItemType,
)

__all__ = [
    "Blocker",
    "Lease",
    "QueueStatus",
    "ReviewRoute",
    "RiskLevel",
    "WorkItemType",
    "WorkflowStage",
    "WorkflowState",
]


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
