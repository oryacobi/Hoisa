"""Agent run records and compact execution summaries."""

from enum import StrEnum

from pydantic import Field

from hoisa.domain.actors import ActorRef
from hoisa.domain.evidence import EvidenceRef
from hoisa.domain.models import BsonObjectId, CollectionRoot, HoisaModel, UtcDatetime
from hoisa.domain.privacy import PublicSafetyClass, RedactionStatus
from hoisa.domain.provenance import SourceProvenance
from hoisa.domain.workflow_state import WorkflowStage


class RunStatus(StrEnum):
    """Lifecycle status for a disposable agent run."""

    STARTED = "started"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELED = "canceled"


class CheckStatus(StrEnum):
    """Status for checks summarized by an agent run."""

    PASSED = "passed"
    FAILED = "failed"
    SKIPPED = "skipped"


class RunnerProfile(HoisaModel):
    """Runner configuration visible to a task packet or run record."""

    runner_type: str = Field(min_length=1)
    profile_name: str = Field(min_length=1)
    sandbox: str = Field(min_length=1)
    network_access: bool = False


class RunBudget(HoisaModel):
    """Bounded execution budget for a run."""

    max_minutes: int = Field(gt=0)
    max_attempts: int = Field(gt=0)


class CommandSummary(HoisaModel):
    """Compact command result without raw logs."""

    command_label: str = Field(min_length=1)
    exit_code: int
    summary: str = Field(min_length=1)
    evidence_refs: tuple[EvidenceRef, ...] = ()


class CheckSummary(HoisaModel):
    """Compact check result for PR handoff and review."""

    name: str = Field(min_length=1)
    status: CheckStatus
    summary: str = Field(min_length=1)
    evidence_refs: tuple[EvidenceRef, ...] = ()


class AgentRun(CollectionRoot):
    """Disposable run attempt for one bounded workflow stage."""

    work_item_id: BsonObjectId
    workflow_stage: WorkflowStage
    runner_profile: RunnerProfile
    budget: RunBudget
    agent: ActorRef
    status: RunStatus
    started_at: UtcDatetime
    completed_at: UtcDatetime | None = None
    command_summaries: tuple[CommandSummary, ...] = ()
    check_summaries: tuple[CheckSummary, ...] = ()
    evidence_refs: tuple[EvidenceRef, ...] = ()
    source_provenance: SourceProvenance
    public_safety: PublicSafetyClass
    redaction_status: RedactionStatus
