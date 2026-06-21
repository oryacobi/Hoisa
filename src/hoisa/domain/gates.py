"""Approval gate and gate decision records."""

from enum import StrEnum
from typing import ClassVar

from antonic import AntDoc
from pydantic import Field

from hoisa.domain.actors import ActorRef
from hoisa.domain.evidence import EvidenceRef
from hoisa.domain.models import HoisaModel, RecordId, UtcDatetime
from hoisa.domain.privacy import PublicSafetyClass, RedactionStatus
from hoisa.domain.provenance import SourceProvenance
from hoisa.domain.workflow_state import RiskLevel, WorkflowStage


class GateType(StrEnum):
    """Kinds of human decisions Hoisa can request."""

    PLAN_APPROVAL = "plan_approval"
    PRIVILEGED_ACTION = "privileged_action"
    SCOPE_CHANGE = "scope_change"
    MERGE_READINESS = "merge_readiness"


class GateStatus(StrEnum):
    """Lifecycle state for an approval gate."""

    WAITING = "waiting"
    APPROVED = "approved"
    CHANGES_REQUESTED = "changes_requested"
    REVIEW_REQUESTED = "review_requested"
    DEFERRED = "deferred"
    EXPIRED = "expired"


class GateOption(StrEnum):
    """Allowed human responses for a gate."""

    APPROVE = "approve"
    REQUEST_CHANGES = "request_changes"
    REQUEST_FRESH_REVIEW = "request_fresh_review"
    DEFER = "defer"


class GateRecommendation(StrEnum):
    """Hoisa's recommendation for a gate."""

    APPROVE = "approve"
    REQUEST_CHANGES = "request_changes"
    REQUEST_FRESH_REVIEW = "request_fresh_review"
    DEFER = "defer"


class GateDecision(HoisaModel):
    """Single-use decision recorded against an approval gate."""

    decision: GateOption
    decided_by: ActorRef
    decided_at: UtcDatetime
    rationale: str = Field(min_length=1)
    source_provenance: SourceProvenance


class ApprovalGate(AntDoc):
    """Structured human approval object with exact authority boundaries."""

    ant_collection: ClassVar[str] = "approval_gates"

    id: RecordId | None = None
    gate_type: GateType
    gate_status: GateStatus
    work_item_id: RecordId
    workflow_stage: WorkflowStage
    risk: RiskLevel
    recommendation: GateRecommendation
    decision_needed: str = Field(min_length=1)
    why_human_needed: str = Field(min_length=1)
    authority_granted: str = Field(min_length=1)
    options: tuple[GateOption, ...] = Field(min_length=1)
    evidence_refs: tuple[EvidenceRef, ...] = Field(min_length=1)
    decision: GateDecision | None = None
    source_provenance: SourceProvenance
    public_safety: PublicSafetyClass
    redaction_status: RedactionStatus
