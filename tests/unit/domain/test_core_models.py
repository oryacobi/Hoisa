from datetime import UTC, datetime

from pydantic import ValidationError
import pytest

from hoisa.domain.actors import ActorRef, ActorType
from hoisa.domain.directives import Directive
from hoisa.domain.events import EventSubject, WorkflowEvent, WorkflowEventType
from hoisa.domain.evidence import EvidenceKind, EvidenceRef, EvidenceRequirement
from hoisa.domain.gates import (
    ApprovalGate,
    GateDecision,
    GateOption,
    GateRecommendation,
    GateStatus,
    GateType,
)
from hoisa.domain.privacy import PublicSafetyClass, RedactionStatus
from hoisa.domain.provenance import SourceProvenance, SourceSystem
from hoisa.domain.runs import RunBudget, RunnerProfile
from hoisa.domain.target_repos import (
    ProjectRef,
    RepositoryProvider,
    RepositoryVisibility,
    TargetRepoRef,
)
from hoisa.domain.task_packets import AllowedAction, TaskPacket
from hoisa.domain.workflow_state import ReviewRoute, RiskLevel, WorkflowStage


def test_collection_roots_normalize_timezone_aware_timestamps() -> None:
    directive = Directive(
        directive_id="directive-1",
        created_at=datetime(2026, 5, 25, 8, 0, tzinfo=UTC),
        updated_at=datetime(2026, 5, 25, 8, 5, tzinfo=UTC),
        project=_project(),
        target_repo=_repo(),
        summary="Define records.",
        body="Define public-safe records.",
        requested_review_route=ReviewRoute.REVIEW_BOTH,
        risk=RiskLevel.HIGH,
        source_provenance=_provenance(),
        public_safety=PublicSafetyClass.PUBLIC_SAFE_SAMPLE,
        redaction_status=RedactionStatus.NOT_REQUIRED,
    )

    assert directive.directive_id == "directive-1"
    assert directive.created_at.tzinfo == UTC
    assert directive.schema_version == 1


def test_naive_datetimes_are_rejected() -> None:
    with pytest.raises(ValidationError, match="timezone-aware"):
        Directive(
            directive_id="directive-1",
            created_at=datetime(2026, 5, 25, 8, 0),
            updated_at=datetime(2026, 5, 25, 8, 5, tzinfo=UTC),
            project=_project(),
            summary="Define records.",
            body="Define public-safe records.",
            requested_review_route=ReviewRoute.REVIEW_BOTH,
            risk=RiskLevel.HIGH,
            source_provenance=_provenance(),
            public_safety=PublicSafetyClass.PUBLIC_SAFE_SAMPLE,
            redaction_status=RedactionStatus.NOT_REQUIRED,
        )


def test_nested_value_objects_do_not_inherit_collection_root_fields() -> None:
    fields = set(EvidenceRef.model_fields)

    assert "evidence_id" in fields
    assert "created_at" not in fields
    assert "updated_at" not in fields
    assert "schema_version" not in fields


def test_gate_records_exact_authority_and_decision_context() -> None:
    decision = GateDecision(
        decision=GateOption.APPROVE,
        decided_by=ActorRef(actor_type=ActorType.HUMAN, actor_id="human-reviewer"),
        decided_at=datetime(2026, 5, 25, 9, 0, tzinfo=UTC),
        rationale="Approved bounded implementation.",
        source_provenance=_provenance(source_system=SourceSystem.HUMAN),
    )
    gate = ApprovalGate(
        gate_id="gate-1",
        created_at=datetime(2026, 5, 25, 8, 30, tzinfo=UTC),
        updated_at=datetime(2026, 5, 25, 9, 0, tzinfo=UTC),
        gate_type=GateType.PLAN_APPROVAL,
        gate_status=GateStatus.APPROVED,
        work_item_id="work-1",
        workflow_stage=WorkflowStage.PLAN_APPROVAL,
        risk=RiskLevel.HIGH,
        recommendation=GateRecommendation.APPROVE,
        decision_needed="Approve the implementation plan.",
        why_human_needed="The plan defines foundational workflow state.",
        authority_granted="Implement only the approved model and schema slice.",
        options=(
            GateOption.APPROVE,
            GateOption.REQUEST_CHANGES,
            GateOption.REQUEST_FRESH_REVIEW,
            GateOption.DEFER,
        ),
        evidence_refs=(_evidence_ref(),),
        decision=decision,
        source_provenance=_provenance(),
        public_safety=PublicSafetyClass.PUBLIC_SAFE_SAMPLE,
        redaction_status=RedactionStatus.NOT_REQUIRED,
    )

    assert gate.authority_granted.startswith("Implement only")
    assert GateOption.REQUEST_FRESH_REVIEW in gate.options
    assert gate.decision is not None
    assert gate.decision.decided_at.tzinfo == UTC


def test_task_packets_bound_context_actions_budget_and_evidence_requirements() -> None:
    packet = TaskPacket(
        packet_id="packet-1",
        work_item_id="work-1",
        created_at=datetime(2026, 5, 25, 10, 0, tzinfo=UTC),
        updated_at=datetime(2026, 5, 25, 10, 0, tzinfo=UTC),
        workflow_stage=WorkflowStage.IMPLEMENTATION,
        target_repo=_repo(),
        objective="Implement the approved model slice.",
        context_refs=(_evidence_ref(),),
        allowed_actions=(
            AllowedAction(
                action_type="edit_repo_files",
                scope="approved-plan-files",
                requires_gate=False,
            ),
        ),
        authority_granted=("Implement only the approved plan.",),
        runner_profile=_runner_profile(),
        budget=RunBudget(max_minutes=45, max_attempts=1),
        evidence_requirements=(
            EvidenceRequirement(
                requirement_id="checks",
                kind=EvidenceKind.CHECK_RUN,
                description="Summarize required checks.",
            ),
        ),
        source_provenance=_provenance(),
        public_safety=PublicSafetyClass.PUBLIC_SAFE_SAMPLE,
        redaction_status=RedactionStatus.NOT_REQUIRED,
    )

    assert packet.context_refs
    assert packet.allowed_actions[0].scope == "approved-plan-files"
    assert packet.budget.max_minutes == 45
    assert packet.evidence_requirements[0].required is True


def test_workflow_events_carry_correlation_provenance_and_evidence() -> None:
    event = WorkflowEvent(
        event_id="event-1",
        event_type=WorkflowEventType.GATE_DECIDED,
        happened_at=datetime(2026, 5, 25, 11, 0, tzinfo=UTC),
        actor=ActorRef(actor_type=ActorType.HUMAN, actor_id="human-reviewer"),
        subject=EventSubject(subject_type="approval_gate", subject_id="gate-1"),
        correlation_id="corr-1",
        causation_id="event-0",
        workflow_stage=WorkflowStage.PLAN_APPROVAL,
        risk=RiskLevel.HIGH,
        public_safety=PublicSafetyClass.PUBLIC_SAFE_SAMPLE,
        payload_schema="gate_decision.v1",
        payload={"decision": "approve"},
        evidence_refs=(_evidence_ref(),),
        source_provenance=_provenance(source_system=SourceSystem.HUMAN),
        redaction_status=RedactionStatus.NOT_REQUIRED,
    )

    assert event.schema_version == 1
    assert event.correlation_id == "corr-1"
    assert event.evidence_refs[0].redaction_status == RedactionStatus.NOT_REQUIRED


def _project() -> ProjectRef:
    return ProjectRef(project_id="project-sample", name="Hoisa Sample")


def _repo() -> TargetRepoRef:
    return TargetRepoRef(
        target_repo_id="repo-sample",
        provider=RepositoryProvider.GITHUB,
        owner="example-org",
        name="example-repo",
        visibility=RepositoryVisibility.PUBLIC,
        project=_project(),
    )


def _provenance(source_system: SourceSystem = SourceSystem.HOISA) -> SourceProvenance:
    return SourceProvenance(
        source_system=source_system,
        source_id="source-sample",
        observed_at=datetime(2026, 5, 25, 8, 0, tzinfo=UTC),
        source_url="https://github.com/example-org/example-repo/issues/6",
        public_safety=PublicSafetyClass.PUBLIC_SAFE_SAMPLE,
    )


def _evidence_ref() -> EvidenceRef:
    return EvidenceRef(
        evidence_id="evidence-plan",
        kind=EvidenceKind.PLAN,
        uri="docs/agent-plans/6-sample-models.md",
        summary="Public-safe approved plan.",
        public_safety=PublicSafetyClass.PUBLIC_SAFE_SAMPLE,
        redaction_status=RedactionStatus.NOT_REQUIRED,
    )


def _runner_profile() -> RunnerProfile:
    return RunnerProfile(
        runner_type="codex",
        profile_name="local-sandbox",
        sandbox="workspace",
        network_access=False,
    )
