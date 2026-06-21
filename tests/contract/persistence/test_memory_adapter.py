import asyncio
from collections.abc import Coroutine
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from hoisa.adapters.persistence.memory import InMemoryPersistenceProvider
from hoisa.domain.actors import ActorRef, ActorType
from hoisa.domain.events import EventSubject, WorkflowEvent
from hoisa.domain.evidence import EvidenceBundle, EvidenceKind, EvidenceRef
from hoisa.domain.gates import (
    ApprovalGate,
    GateOption,
    GateRecommendation,
    GateStatus,
    GateType,
)
from hoisa.domain.privacy import PublicSafetyClass, RedactionStatus
from hoisa.domain.provenance import ContentHash, SourceProvenance, SourceSystem
from hoisa.domain.runs import AgentRun, RunBudget, RunnerProfile, RunStatus
from hoisa.domain.sources import (
    SourceConnection,
    SourceConnectionStatus,
    SourceObservation,
    SyncCursor,
)
from hoisa.domain.target_repos import (
    Project,
    ProjectRef,
    RepositoryProvider,
    RepositoryVisibility,
    TargetRepo,
    TargetRepoRef,
)
from hoisa.domain.tool_control import (
    ActionRequest,
    ActionRequestStatus,
    ToolConnection,
    ToolConnectionStatus,
    ToolInvocation,
    ToolInvocationStatus,
    ToolPolicy,
    ToolPolicyDecision,
)
from hoisa.domain.work_items import TrackerIssueRef, WorkItem
from hoisa.domain.workflow_event_types import WorkflowEventType
from hoisa.domain.workflow_state import (
    Blocker,
    Lease,
    QueueStatus,
    ReviewRoute,
    RiskLevel,
    WorkflowStage,
    WorkflowState,
    WorkflowStateRecord,
    WorkItemType,
)
from hoisa.ports.persistence import (
    DuplicateRecordError,
    LeaseLookupQuery,
    RepoLookup,
    RunnableWorkQuery,
    SourceObservationQuery,
    SyncCursorKey,
    ToolActionQuery,
    WaitingGateQuery,
)


def test_repositories_save_and_fetch_current_state_records() -> None:
    provider = InMemoryPersistenceProvider()
    run(provider.projects.save(_project()))
    run(provider.target_repos.save(_target_repo()))
    run(provider.source_connections.save(_source_connection()))
    run(provider.source_observations.save(_source_observation()))
    run(provider.sync_cursors.save(_sync_cursor()))
    run(provider.work_items.save(_work_item("work-1", issue_number=9)))
    run(provider.workflow_states.save(_state("work-1")))
    run(provider.gates.save(_gate("gate-1", work_item_id="work-1")))
    run(provider.agent_runs.save(_agent_run("run-1", work_item_id="work-1")))
    run(provider.evidence_bundles.save(_evidence_bundle("bundle-1", subject_id="work-1")))
    run(provider.tool_connections.save(_tool_connection()))
    run(provider.tool_policies.save(_tool_policy()))
    run(provider.action_requests.save(_action_request()))
    run(provider.tool_invocations.save(_tool_invocation()))
    run(provider.workflow_events.append(_event("event-1", _time(2))))

    assert run(provider.projects.get("project-sample")) is not None
    assert run(provider.target_repos.get("repo-sample")) is not None
    assert run(provider.target_repos.get_by_provider(_repo_lookup())) is not None
    assert len(run(provider.target_repos.list_by_project("project-sample"))) == 1
    assert run(provider.source_connections.get("source-github")) is not None
    assert len(run(provider.source_observations.find_by_source(_observation_query()))) == 1
    assert run(provider.sync_cursors.get(_cursor_key())) is not None
    assert run(provider.work_items.find_by_tracker_issue(provider="github", issue_number=9))
    assert run(provider.workflow_states.get("work-1")) is not None
    assert len(run(provider.gates.list_by_work_item("work-1"))) == 1
    assert len(run(provider.agent_runs.list_by_work_item("work-1"))) == 1
    assert (
        len(
            run(
                provider.evidence_bundles.list_by_subject(
                    subject_type="work_item",
                    subject_id="work-1",
                )
            )
        )
        == 1
    )
    assert len(run(provider.tool_connections.list_by_project("project-sample"))) == 1
    assert len(run(provider.tool_policies.find_for_action(_tool_query()))) == 1
    assert len(run(provider.action_requests.list_by_status(ActionRequestStatus.GATED))) == 1
    assert len(run(provider.action_requests.list_for_gate("gate-1"))) == 1
    assert len(run(provider.tool_invocations.list_for_action_request("action-1"))) == 1
    assert len(run(provider.tool_invocations.list_by_tool_action(_tool_query()))) == 1
    assert run(provider.workflow_events.get("event-1")) is not None


def test_unique_keys_are_rejected_deterministically() -> None:
    provider = InMemoryPersistenceProvider()
    run(provider.target_repos.save(_target_repo("repo-1")))
    run(provider.source_observations.save(_source_observation("observation-1")))
    run(provider.sync_cursors.save(_sync_cursor("cursor-1")))
    run(provider.work_items.save(_work_item("work-1", issue_number=9)))
    run(provider.tool_policies.save(_tool_policy("policy-1")))
    run(provider.workflow_events.append(_event("event-1", _time())))

    with pytest.raises(DuplicateRecordError, match="target repository"):
        run(provider.target_repos.save(_target_repo("repo-2")))
    with pytest.raises(DuplicateRecordError, match="source observation"):
        run(provider.source_observations.save(_source_observation("observation-2")))
    with pytest.raises(DuplicateRecordError, match="sync cursor"):
        run(provider.sync_cursors.save(_sync_cursor("cursor-2")))
    with pytest.raises(DuplicateRecordError, match="tracker issue"):
        run(provider.work_items.save(_work_item("work-2", issue_number=9)))
    with pytest.raises(DuplicateRecordError, match="tool policy"):
        run(provider.tool_policies.save(_tool_policy("policy-2")))
    with pytest.raises(DuplicateRecordError, match="Workflow event"):
        run(provider.workflow_events.append(_event("event-1", _time(1))))


def test_runnable_gate_and_lease_queries_are_intention_revealing() -> None:
    provider = InMemoryPersistenceProvider()
    now = _time(10)
    run(provider.work_items.save(_work_item("eligible", issue_number=1)))
    run(provider.work_items.save(_work_item("active", issue_number=2)))
    run(provider.work_items.save(_work_item("expired", issue_number=3)))
    run(provider.work_items.save(_work_item("blocked", issue_number=4)))
    run(provider.workflow_states.save(_state("eligible")))
    run(
        provider.workflow_states.save(
            _state(
                "active",
                lease=Lease(worker_id="Codex-1", claimed_at=_time(), expires_at=_time(20)),
            )
        )
    )
    run(
        provider.workflow_states.save(
            _state(
                "expired",
                lease=Lease(worker_id="Codex-2", claimed_at=_time(), expires_at=_time(5)),
            )
        )
    )
    run(
        provider.workflow_states.save(
            _state(
                "blocked",
                blockers=(Blocker(blocker_id="blocker-1", summary="Waiting.", created_at=_time()),),
            )
        )
    )
    run(provider.gates.save(_gate("gate-1", work_item_id="eligible")))

    runnable = run(
        provider.work_items.find_runnable(
            RunnableWorkQuery(workflow_stage=WorkflowStage.IMPLEMENTATION, now=now)
        )
    )
    active = run(provider.workflow_states.list_active_leases(LeaseLookupQuery(now=now)))
    expired = run(provider.workflow_states.list_expired_leases(LeaseLookupQuery(now=now)))
    waiting = run(provider.gates.list_waiting(WaitingGateQuery(tracker_issue_number=1)))

    assert [item.id for item in runnable] == ["eligible", "expired"]
    assert [record.work_item_id for record in active] == ["active"]
    assert [record.work_item_id for record in expired] == ["expired"]
    assert [gate.id for gate in waiting] == ["gate-1"]


def test_events_are_append_only_and_query_order_is_deterministic() -> None:
    provider = InMemoryPersistenceProvider()
    subject = EventSubject(subject_type="work_item", subject_id="work-1")
    run(provider.workflow_events.append(_event("event-2", _time(2), subject=subject)))
    run(provider.workflow_events.append(_event("event-1", _time(1), subject=subject)))
    run(
        provider.workflow_events.append(
            _event(
                "event-3",
                _time(3),
                subject=EventSubject(subject_type="work_item", subject_id="work-2"),
                correlation_id="other",
            )
        )
    )

    by_subject = run(provider.workflow_events.list_for_subject(subject))
    by_correlation = run(provider.workflow_events.list_for_correlation("corr-1"))
    recent = run(provider.workflow_events.list_recent(limit=2))

    assert [event.id for event in by_subject] == ["event-1", "event-2"]
    assert [event.id for event in by_correlation] == ["event-1", "event-2"]
    assert [event.id for event in recent] == ["event-2", "event-3"]


def test_provider_instances_do_not_share_state() -> None:
    first = InMemoryPersistenceProvider()
    second = InMemoryPersistenceProvider()
    run(first.projects.save(_project()))

    assert len(run(first.projects.list_all())) == 1
    assert len(run(second.projects.list_all())) == 0


def run[T](coro: Coroutine[Any, Any, T]) -> T:
    return asyncio.run(coro)


def _project(project_id: str = "project-sample") -> Project:
    return Project(
        id=project_id,
        name="Sample Project",
        summary="Public-safe sample project.",
        created_at=_time(),
        updated_at=_time(),
        source_provenance=_provenance(),
        public_safety=PublicSafetyClass.PUBLIC_SAFE_SAMPLE,
        redaction_status=RedactionStatus.NOT_REQUIRED,
    )


def _target_repo(target_repo_id: str = "repo-sample") -> TargetRepo:
    return TargetRepo(
        id=target_repo_id,
        provider=RepositoryProvider.GITHUB,
        owner="example-org",
        name="example-repo",
        visibility=RepositoryVisibility.PUBLIC,
        project=_project_ref(),
        default_branch="main",
        created_at=_time(),
        updated_at=_time(),
        source_provenance=_provenance(),
        public_safety=PublicSafetyClass.PUBLIC_SAFE_SAMPLE,
        redaction_status=RedactionStatus.NOT_REQUIRED,
    )


def _source_connection() -> SourceConnection:
    return SourceConnection(
        id="source-github",
        project=_project_ref(),
        source_system=SourceSystem.GITHUB,
        display_name="Example GitHub",
        status=SourceConnectionStatus.ACTIVE,
        target_repo=_target_repo_ref(),
        created_at=_time(),
        updated_at=_time(),
        source_provenance=_provenance(source_system=SourceSystem.GITHUB),
        public_safety=PublicSafetyClass.PUBLIC_SAFE_SAMPLE,
        redaction_status=RedactionStatus.NOT_REQUIRED,
    )


def _source_observation(observation_id: str = "observation-1") -> SourceObservation:
    return SourceObservation(
        id=observation_id,
        source_connection_id="source-github",
        external_id="issue-9",
        content_hash=_hash(),
        summary="Issue metadata summary.",
        payload_schema="github_issue_summary.v1",
        payload={"issue_number": 9},
        created_at=_time(),
        updated_at=_time(),
        source_provenance=_provenance(source_system=SourceSystem.GITHUB),
        public_safety=PublicSafetyClass.PUBLIC_SAFE_SAMPLE,
        redaction_status=RedactionStatus.NOT_REQUIRED,
    )


def _sync_cursor(cursor_id: str = "cursor-1") -> SyncCursor:
    return SyncCursor(
        id=cursor_id,
        source_connection_id="source-github",
        cursor_name="issues",
        cursor_value="cursor-value",
        created_at=_time(),
        updated_at=_time(),
        source_provenance=_provenance(source_system=SourceSystem.GITHUB),
        public_safety=PublicSafetyClass.PUBLIC_SAFE_SAMPLE,
        redaction_status=RedactionStatus.NOT_REQUIRED,
    )


def _work_item(work_item_id: str, *, issue_number: int) -> WorkItem:
    return WorkItem(
        id=work_item_id,
        item_type=WorkItemType.TASK,
        title=f"Issue {issue_number}",
        goal="Implement a public-safe sample task.",
        target_repo=_target_repo_ref(),
        tracker_issue=TrackerIssueRef(
            tracker_issue_id=f"issue-{issue_number}",
            provider="github",
            issue_number=issue_number,
            title=f"Issue {issue_number}",
            url=f"https://github.com/example-org/example-repo/issues/{issue_number}",
        ),
        workflow_stage=WorkflowStage.IMPLEMENTATION,
        status=QueueStatus.TODO,
        review_route=ReviewRoute.REVIEW_BOTH,
        risk=RiskLevel.HIGH,
        quality_status="ready",
        created_at=_time(issue_number),
        updated_at=_time(issue_number),
        source_provenance=_provenance(),
        public_safety=PublicSafetyClass.PUBLIC_SAFE_SAMPLE,
        redaction_status=RedactionStatus.NOT_REQUIRED,
    )


def _state(
    work_item_id: str,
    *,
    lease: Lease | None = None,
    blockers: tuple[Blocker, ...] = (),
) -> WorkflowStateRecord:
    return WorkflowStateRecord(
        id=work_item_id,
        work_item_id=work_item_id,
        state=WorkflowState(
            stage=WorkflowStage.IMPLEMENTATION,
            status=QueueStatus.TODO,
            review_route=ReviewRoute.REVIEW_BOTH,
            risk=RiskLevel.HIGH,
            lease=lease,
            blockers=blockers,
        ),
        created_at=_time(),
        updated_at=_time(),
        source_provenance=_provenance(),
        public_safety=PublicSafetyClass.PUBLIC_SAFE_SAMPLE,
        redaction_status=RedactionStatus.NOT_REQUIRED,
    )


def _gate(gate_id: str, *, work_item_id: str) -> ApprovalGate:
    return ApprovalGate(
        id=gate_id,
        gate_type=GateType.PLAN_APPROVAL,
        gate_status=GateStatus.WAITING,
        work_item_id=work_item_id,
        workflow_stage=WorkflowStage.PLAN_APPROVAL,
        risk=RiskLevel.HIGH,
        recommendation=GateRecommendation.APPROVE,
        decision_needed="Approve implementation.",
        why_human_needed="A human approval gate is required.",
        authority_granted="Implement only the approved plan.",
        options=(GateOption.APPROVE, GateOption.REQUEST_CHANGES),
        evidence_refs=(_evidence_ref(),),
        created_at=_time(),
        updated_at=_time(),
        source_provenance=_provenance(),
        public_safety=PublicSafetyClass.PUBLIC_SAFE_SAMPLE,
        redaction_status=RedactionStatus.NOT_REQUIRED,
    )


def _agent_run(run_id: str, *, work_item_id: str) -> AgentRun:
    return AgentRun(
        id=run_id,
        work_item_id=work_item_id,
        workflow_stage=WorkflowStage.IMPLEMENTATION,
        runner_profile=RunnerProfile(
            runner_type="codex",
            profile_name="local",
            sandbox="workspace",
        ),
        budget=RunBudget(max_minutes=30, max_attempts=1),
        agent=ActorRef(actor_type=ActorType.AGENT, actor_id="codex"),
        status=RunStatus.STARTED,
        started_at=_time(),
        created_at=_time(),
        updated_at=_time(),
        source_provenance=_provenance(),
        public_safety=PublicSafetyClass.PUBLIC_SAFE_SAMPLE,
        redaction_status=RedactionStatus.NOT_REQUIRED,
    )


def _evidence_bundle(bundle_id: str, *, subject_id: str) -> EvidenceBundle:
    return EvidenceBundle(
        id=bundle_id,
        subject_type="work_item",
        subject_id=subject_id,
        refs=(_evidence_ref(),),
        created_at=_time(),
        updated_at=_time(),
        source_provenance=_provenance(),
        public_safety=PublicSafetyClass.PUBLIC_SAFE_SAMPLE,
        redaction_status=RedactionStatus.NOT_REQUIRED,
    )


def _tool_connection() -> ToolConnection:
    return ToolConnection(
        id="tool-github",
        project=_project_ref(),
        tool_type="github",
        display_name="GitHub",
        status=ToolConnectionStatus.ACTIVE,
        created_at=_time(),
        updated_at=_time(),
        source_provenance=_provenance(),
        public_safety=PublicSafetyClass.PUBLIC_SAFE_SAMPLE,
        redaction_status=RedactionStatus.NOT_REQUIRED,
    )


def _tool_policy(tool_policy_id: str = "policy-1") -> ToolPolicy:
    return ToolPolicy(
        id=tool_policy_id,
        project=_project_ref(),
        tool_type="github",
        action_type="create_pull_request",
        decision=ToolPolicyDecision.REQUIRE_GATE,
        summary="Require gate for pull request creation.",
        created_at=_time(),
        updated_at=_time(),
        source_provenance=_provenance(),
        public_safety=PublicSafetyClass.PUBLIC_SAFE_SAMPLE,
        redaction_status=RedactionStatus.NOT_REQUIRED,
    )


def _action_request() -> ActionRequest:
    return ActionRequest(
        id="action-1",
        project=_project_ref(),
        tool_type="github",
        action_type="create_pull_request",
        status=ActionRequestStatus.GATED,
        summary="Request PR creation.",
        required_gate_id="gate-1",
        created_at=_time(),
        updated_at=_time(),
        source_provenance=_provenance(),
        public_safety=PublicSafetyClass.PUBLIC_SAFE_SAMPLE,
        redaction_status=RedactionStatus.NOT_REQUIRED,
    )


def _tool_invocation() -> ToolInvocation:
    return ToolInvocation(
        id="invocation-1",
        tool_type="github",
        action_type="create_pull_request",
        status=ToolInvocationStatus.SKIPPED,
        happened_at=_time(),
        summary="Skipped until approval.",
        action_request_id="action-1",
        created_at=_time(),
        updated_at=_time(),
        source_provenance=_provenance(),
        public_safety=PublicSafetyClass.PUBLIC_SAFE_SAMPLE,
        redaction_status=RedactionStatus.NOT_REQUIRED,
    )


def _event(
    event_id: str,
    happened_at: datetime,
    *,
    subject: EventSubject | None = None,
    correlation_id: str = "corr-1",
) -> WorkflowEvent:
    return WorkflowEvent(
        id=event_id,
        event_type=WorkflowEventType.WORK_ITEM_SELECTED,
        happened_at=happened_at,
        actor=ActorRef(actor_type=ActorType.AGENT, actor_id="codex"),
        subject=subject or EventSubject(subject_type="work_item", subject_id="work-1"),
        correlation_id=correlation_id,
        workflow_stage=WorkflowStage.IMPLEMENTATION,
        risk=RiskLevel.HIGH,
        public_safety=PublicSafetyClass.PUBLIC_SAFE_SAMPLE,
        payload_schema="work_selection.v1",
        payload={"action": "implement"},
        source_provenance=_provenance(),
        redaction_status=RedactionStatus.NOT_REQUIRED,
    )


def _time(minutes: int = 0) -> datetime:
    return datetime(2026, 5, 25, 12, 0, tzinfo=UTC) + timedelta(minutes=minutes)


def _project_ref() -> ProjectRef:
    return ProjectRef(project_id="project-sample", name="Sample Project")


def _target_repo_ref() -> TargetRepoRef:
    return TargetRepoRef(
        target_repo_id="repo-sample",
        provider=RepositoryProvider.GITHUB,
        owner="example-org",
        name="example-repo",
        visibility=RepositoryVisibility.PUBLIC,
        project=_project_ref(),
    )


def _repo_lookup() -> RepoLookup:
    return RepoLookup(
        provider=RepositoryProvider.GITHUB,
        owner="example-org",
        name="example-repo",
    )


def _provenance(source_system: SourceSystem = SourceSystem.HOISA) -> SourceProvenance:
    return SourceProvenance(
        source_system=source_system,
        source_id="source-sample",
        observed_at=_time(),
        source_url="https://github.com/example-org/example-repo/issues/9",
        public_safety=PublicSafetyClass.PUBLIC_SAFE_SAMPLE,
    )


def _hash() -> ContentHash:
    return ContentHash(algorithm="sha256", value="abc123")


def _evidence_ref() -> EvidenceRef:
    return EvidenceRef(
        evidence_id="evidence-plan",
        kind=EvidenceKind.PLAN,
        uri="docs/agent-plans/9-sample.md",
        summary="Public-safe plan.",
        public_safety=PublicSafetyClass.PUBLIC_SAFE_SAMPLE,
        redaction_status=RedactionStatus.NOT_REQUIRED,
    )


def _observation_query() -> SourceObservationQuery:
    return SourceObservationQuery(
        source_connection_id="source-github",
        external_id="issue-9",
        content_hash_value="abc123",
    )


def _cursor_key() -> SyncCursorKey:
    return SyncCursorKey(source_connection_id="source-github", cursor_name="issues")


def _tool_query() -> ToolActionQuery:
    return ToolActionQuery(
        project_id="project-sample",
        tool_type="github",
        action_type="create_pull_request",
    )
