"""Workflow state vocabulary shared by Hoisa domain records."""

from typing import ClassVar

from pydantic import Field

from hoisa.domain.models import CollectionRoot, HoisaModel, UtcDatetime
from hoisa.domain.privacy import PublicSafetyClass, RedactionStatus
from hoisa.domain.provenance import SourceProvenance
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
    "WorkflowStateRecord",
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


class WorkflowStateRecord(CollectionRoot):
    """Persisted workflow-state snapshot keyed by work item."""

    ant_collection: ClassVar[str] = "workflow_states"

    work_item_id: str = Field(min_length=1)
    state: WorkflowState
    source_provenance: SourceProvenance
    public_safety: PublicSafetyClass
    redaction_status: RedactionStatus
