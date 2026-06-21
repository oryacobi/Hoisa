"""Work item domain records shared by application workflows and ports."""

from typing import ClassVar

from antonic import AntIndex
from pydantic import Field

from hoisa.domain.evidence import EvidenceRef
from hoisa.domain.models import ASCENDING, CollectionRoot, HoisaModel
from hoisa.domain.privacy import PublicSafetyClass, RedactionStatus
from hoisa.domain.provenance import SourceProvenance
from hoisa.domain.target_repos import TargetRepoRef
from hoisa.domain.work_item_refs import WorkItemRef
from hoisa.domain.workflow_state import (
    QueueStatus,
    ReviewRoute,
    RiskLevel,
    WorkflowStage,
    WorkItemType,
)

__all__ = [
    "TrackerIssueRef",
    "WorkItem",
    "WorkItemRef",
    "WorkflowStage",
]


class TrackerIssueRef(HoisaModel):
    """Public-safe reference to a tracker issue."""

    tracker_issue_id: str = Field(min_length=1)
    provider: str = Field(min_length=1)
    issue_number: int = Field(ge=1)
    title: str = Field(min_length=1)
    url: str


class WorkItem(CollectionRoot):
    """Agent-ready unit of Hoisa workflow."""

    ant_collection: ClassVar[str] = "work_items"
    ant_indexes: ClassVar[tuple[AntIndex, ...]] = (
        AntIndex(
            [("tracker_issue.provider", ASCENDING), ("tracker_issue.issue_number", ASCENDING)],
            unique=True,
            sparse=True,
            name="uniq_work_item_tracker_issue",
        ),
    )

    item_type: WorkItemType
    title: str = Field(min_length=1)
    goal: str = Field(min_length=1)
    target_repo: TargetRepoRef
    tracker_issue: TrackerIssueRef | None = None
    workflow_stage: WorkflowStage
    status: QueueStatus
    review_route: ReviewRoute
    risk: RiskLevel
    quality_status: str = Field(min_length=1)
    plan_ref: str | None = None
    pull_request_ref: str | None = None
    blocker_summaries: tuple[str, ...] = ()
    evidence_refs: tuple[EvidenceRef, ...] = ()
    source_provenance: SourceProvenance
    public_safety: PublicSafetyClass
    redaction_status: RedactionStatus
