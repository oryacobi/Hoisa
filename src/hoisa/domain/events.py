"""Append-only workflow event envelope."""

from enum import StrEnum

from pydantic import Field

from hoisa.domain.actors import ActorRef
from hoisa.domain.evidence import EvidenceRef
from hoisa.domain.models import HoisaModel, UtcDatetime
from hoisa.domain.privacy import PublicSafetyClass, RedactionStatus
from hoisa.domain.provenance import SourceProvenance
from hoisa.domain.workflow_state import RiskLevel, WorkflowStage

JsonScalar = str | int | float | bool | None


class EventSubject(HoisaModel):
    """Workflow event subject reference."""

    subject_type: str = Field(min_length=1)
    subject_id: str = Field(min_length=1)


class WorkflowEventType(StrEnum):
    """Core event families recorded by the Hoisa workflow."""

    DIRECTIVE_CAPTURED = "directive.captured"
    SOURCE_SYNCED = "source.synced"
    SOURCE_CONFLICT_DETECTED = "source.conflict_detected"
    ISSUE_QUALITY_CHECKED = "issue.quality_checked"
    WORK_ITEM_SELECTED = "work_item.selected"
    LEASE_CLAIMED = "lease.claimed"
    TASK_PACKET_CREATED = "task_packet.created"
    PLAN_CREATED = "plan.created"
    PLAN_REVIEW_REQUESTED = "plan.review_requested"
    GATE_CREATED = "gate.created"
    GATE_DECIDED = "gate.decided"
    AGENT_RUN_STARTED = "agent_run.started"
    AGENT_RUN_COMPLETED = "agent_run.completed"
    CHECKS_COMPLETED = "checks.completed"
    PR_OPENED = "pr.opened"
    REVIEW_READY = "review.ready"
    INCIDENT_RECORDED = "incident.recorded"
    RETROSPECTIVE_CREATED = "retrospective.created"


class WorkflowEvent(HoisaModel):
    """Structured event for audit, causation, and retrospective queries."""

    event_id: str = Field(min_length=1)
    event_type: WorkflowEventType
    happened_at: UtcDatetime
    actor: ActorRef
    subject: EventSubject
    correlation_id: str = Field(min_length=1)
    causation_id: str | None = None
    workflow_stage: WorkflowStage
    risk: RiskLevel
    public_safety: PublicSafetyClass
    payload_schema: str = Field(min_length=1)
    payload: dict[str, JsonScalar] = Field(default_factory=dict)
    evidence_refs: tuple[EvidenceRef, ...] = ()
    source_provenance: SourceProvenance | None = None
    redaction_status: RedactionStatus
    schema_version: int = Field(default=1, ge=1)
