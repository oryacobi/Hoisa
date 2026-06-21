"""Append-only workflow event envelope."""

from typing import ClassVar

from pydantic import Field

from hoisa.domain.actors import ActorRef
from hoisa.domain.evidence import EvidenceRef
from hoisa.domain.models import CollectionRoot, HoisaModel, UtcDatetime
from hoisa.domain.privacy import PublicSafetyClass, RedactionStatus
from hoisa.domain.provenance import SourceProvenance
from hoisa.domain.workflow_event_types import WorkflowEventType
from hoisa.domain.workflow_state import RiskLevel, WorkflowStage

JsonScalar = str | int | float | bool | None

__all__ = [
    "EventSubject",
    "JsonScalar",
    "WorkflowEvent",
    "WorkflowEventType",
]


class EventSubject(HoisaModel):
    """Workflow event subject reference."""

    subject_type: str = Field(min_length=1)
    subject_id: str = Field(min_length=1)


class WorkflowEvent(CollectionRoot):
    """Structured event for audit, causation, and retrospective queries."""

    ant_collection: ClassVar[str] = "workflow_events"

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
