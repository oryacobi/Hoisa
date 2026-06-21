"""Tool-control records stored before any external action is performed."""

from enum import StrEnum
from typing import ClassVar

from antonic import AntDoc, AntIndex
from pydantic import Field

from hoisa.domain.evidence import EvidenceRef
from hoisa.domain.models import ASCENDING, RecordId, UtcDatetime
from hoisa.domain.privacy import PublicSafetyClass, RedactionStatus
from hoisa.domain.provenance import SourceProvenance
from hoisa.domain.target_repos import ProjectRef


class ToolConnectionStatus(StrEnum):
    """Lifecycle status for a configured tool connection."""

    ACTIVE = "active"
    DISABLED = "disabled"
    ARCHIVED = "archived"


class ToolPolicyDecision(StrEnum):
    """Policy decision Hoisa records before handling an action request."""

    ALLOW = "allow"
    DENY = "deny"
    REQUIRE_GATE = "require_gate"


class ActionRequestStatus(StrEnum):
    """Lifecycle status for a requested external tool action."""

    REQUESTED = "requested"
    ALLOWED = "allowed"
    DENIED = "denied"
    GATED = "gated"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELED = "canceled"


class ToolInvocationStatus(StrEnum):
    """Result status for an audited tool invocation attempt."""

    SUCCEEDED = "succeeded"
    FAILED = "failed"
    DENIED = "denied"
    SKIPPED = "skipped"


class ToolConnection(AntDoc):
    """Current-state record for a configured tool integration."""

    ant_collection: ClassVar[str] = "tool_connections"

    id: RecordId | None = None
    project: ProjectRef
    tool_type: str = Field(min_length=1)
    display_name: str = Field(min_length=1)
    status: ToolConnectionStatus
    allowed_action_summaries: tuple[str, ...] = ()
    source_provenance: SourceProvenance
    public_safety: PublicSafetyClass
    redaction_status: RedactionStatus


class ToolPolicy(AntDoc):
    """Policy record for a tool action type."""

    ant_collection: ClassVar[str] = "tool_policies"
    ant_indexes: ClassVar[tuple[AntIndex, ...]] = (
        AntIndex(
            [
                ("project.project_id", ASCENDING),
                ("tool_type", ASCENDING),
                ("action_type", ASCENDING),
            ],
            unique=True,
            name="uniq_tool_policy_identity",
        ),
    )

    id: RecordId | None = None
    project: ProjectRef
    tool_type: str = Field(min_length=1)
    action_type: str = Field(min_length=1)
    decision: ToolPolicyDecision
    required_gate_type: str | None = None
    summary: str = Field(min_length=1)
    source_provenance: SourceProvenance
    public_safety: PublicSafetyClass
    redaction_status: RedactionStatus


class ActionRequest(AntDoc):
    """Requested external action, recorded before execution authority exists."""

    ant_collection: ClassVar[str] = "action_requests"

    id: RecordId | None = None
    project: ProjectRef
    tool_type: str = Field(min_length=1)
    action_type: str = Field(min_length=1)
    status: ActionRequestStatus
    summary: str = Field(min_length=1)
    work_item_id: RecordId | None = None
    tool_connection_id: RecordId | None = None
    required_gate_id: RecordId | None = None
    evidence_refs: tuple[EvidenceRef, ...] = ()
    source_provenance: SourceProvenance
    public_safety: PublicSafetyClass
    redaction_status: RedactionStatus


class ToolInvocation(AntDoc):
    """Audited result of a tool invocation attempt."""

    ant_collection: ClassVar[str] = "tool_invocations"

    id: RecordId | None = None
    tool_type: str = Field(min_length=1)
    action_type: str = Field(min_length=1)
    status: ToolInvocationStatus
    happened_at: UtcDatetime
    summary: str = Field(min_length=1)
    action_request_id: RecordId | None = None
    tool_connection_id: RecordId | None = None
    evidence_refs: tuple[EvidenceRef, ...] = ()
    source_provenance: SourceProvenance
    public_safety: PublicSafetyClass
    redaction_status: RedactionStatus
