"""Bounded task packet records passed to disposable agents."""

from typing import ClassVar

from pydantic import Field

from hoisa.domain.evidence import EvidenceRef, EvidenceRequirement
from hoisa.domain.models import CollectionRoot, HoisaModel
from hoisa.domain.privacy import PublicSafetyClass, RedactionStatus
from hoisa.domain.provenance import SourceProvenance
from hoisa.domain.runs import RunBudget, RunnerProfile
from hoisa.domain.target_repos import TargetRepoRef
from hoisa.domain.workflow_state import WorkflowStage


class AllowedAction(HoisaModel):
    """Action authority granted to a runner inside a task packet."""

    action_type: str = Field(min_length=1)
    scope: str = Field(min_length=1)
    requires_gate: bool = False


class TaskPacket(CollectionRoot):
    """Bounded context and authority for one agent run."""

    ant_collection: ClassVar[str] = "task_packets"

    work_item_id: str = Field(min_length=1)
    workflow_stage: WorkflowStage
    target_repo: TargetRepoRef
    objective: str = Field(min_length=1)
    context_refs: tuple[EvidenceRef, ...] = Field(min_length=1)
    allowed_actions: tuple[AllowedAction, ...] = ()
    authority_granted: tuple[str, ...] = ()
    runner_profile: RunnerProfile
    budget: RunBudget
    evidence_requirements: tuple[EvidenceRequirement, ...] = Field(min_length=1)
    source_provenance: SourceProvenance
    public_safety: PublicSafetyClass
    redaction_status: RedactionStatus
