from collections.abc import Awaitable
from datetime import UTC, datetime, timedelta

import pytest

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
    PersistenceProvider,
    RepoLookup,
    RunnableWorkQuery,
    SourceObservationQuery,
    SyncCursorKey,
    ToolActionQuery,
    WaitingGateQuery,
)


async def assert_repositories_save_and_fetch_current_state_records(
    provider: PersistenceProvider,
) -> None:
    await provider.projects.save(project())
    await provider.target_repos.save(target_repo())
    await provider.source_connections.save(source_connection())
    await provider.source_observations.save(source_observation())
    await provider.sync_cursors.save(sync_cursor())
    await provider.work_items.save(work_item("work-1", issue_number=9))
    await provider.workflow_states.save(state("work-1"))
    await provider.gates.save(gate("gate-1", work_item_id="work-1"))
    await provider.agent_runs.save(agent_run("run-1", work_item_id="work-1"))
    await provider.evidence_bundles.save(evidence_bundle("bundle-1", subject_id="work-1"))
    await provider.tool_connections.save(tool_connection())
    await provider.tool_policies.save(tool_policy())
    await provider.action_requests.save(action_request())
    await provider.tool_invocations.save(tool_invocation())
    await provider.workflow_events.append(event("event-1", time_at(2)))

    assert await provider.projects.get("project-sample") is not None
    assert await provider.target_repos.get("repo-sample") is not None
    assert await provider.target_repos.get_by_provider(repo_lookup()) is not None
    assert len(await provider.target_repos.list_by_project("project-sample")) == 1
    assert await provider.source_connections.get("source-github") is not None
    assert len(await provider.source_observations.find_by_source(observation_query())) == 1
    assert await provider.sync_cursors.get(cursor_key()) is not None
    assert await provider.work_items.find_by_tracker_issue(provider="github", issue_number=9)
    assert await provider.workflow_states.get("work-1") is not None
    assert len(await provider.gates.list_by_work_item("work-1")) == 1
    assert len(await provider.agent_runs.list_by_work_item("work-1")) == 1
    assert (
        len(
            await provider.evidence_bundles.list_by_subject(
                subject_type="work_item",
                subject_id="work-1",
            )
        )
        == 1
    )
    assert len(await provider.tool_connections.list_by_project("project-sample")) == 1
    assert len(await provider.tool_policies.find_for_action(tool_query())) == 1
    assert len(await provider.action_requests.list_by_status(ActionRequestStatus.GATED)) == 1
    assert len(await provider.action_requests.list_for_gate("gate-1")) == 1
    assert len(await provider.tool_invocations.list_for_action_request("action-1")) == 1
    assert len(await provider.tool_invocations.list_by_tool_action(tool_query())) == 1
    assert await provider.workflow_events.get("event-1") is not None


async def assert_unique_keys_are_rejected_deterministically(
    provider: PersistenceProvider,
) -> None:
    await provider.target_repos.save(target_repo("repo-1"))
    await provider.source_observations.save(source_observation("observation-1"))
    await provider.sync_cursors.save(sync_cursor("cursor-1"))
    await provider.work_items.save(work_item("work-1", issue_number=9))
    await provider.tool_policies.save(tool_policy("policy-1"))
    await provider.workflow_events.append(event("event-1", time_at()))

    with pytest.raises(DuplicateRecordError, match="target repository"):
        await provider.target_repos.save(target_repo("repo-2"))
    with pytest.raises(DuplicateRecordError, match="source observation"):
        await provider.source_observations.save(source_observation("observation-2"))
    with pytest.raises(DuplicateRecordError, match="sync cursor"):
        await provider.sync_cursors.save(sync_cursor("cursor-2"))
    with pytest.raises(DuplicateRecordError, match="tracker issue"):
        await provider.work_items.save(work_item("work-2", issue_number=9))
    with pytest.raises(DuplicateRecordError, match="tool policy"):
        await provider.tool_policies.save(tool_policy("policy-2"))
    with pytest.raises(DuplicateRecordError, match="Workflow event"):
        await provider.workflow_events.append(event("event-1", time_at(1)))


async def assert_runnable_gate_and_lease_queries_are_intention_revealing(
    provider: PersistenceProvider,
) -> None:
    now = time_at(10)
    await provider.work_items.save(work_item("eligible", issue_number=1))
    await provider.work_items.save(work_item("active", issue_number=2))
    await provider.work_items.save(work_item("expired", issue_number=3))
    await provider.work_items.save(work_item("blocked", issue_number=4))
    await provider.workflow_states.save(state("eligible"))
    await provider.workflow_states.save(
        state(
            "active",
            lease=Lease(worker_id="Codex-1", claimed_at=time_at(), expires_at=time_at(20)),
        )
    )
    await provider.workflow_states.save(
        state(
            "expired",
            lease=Lease(worker_id="Codex-2", claimed_at=time_at(), expires_at=time_at(5)),
        )
    )
    await provider.workflow_states.save(
        state(
            "blocked",
            blockers=(Blocker(blocker_id="blocker-1", summary="Waiting.", created_at=time_at()),),
        )
    )
    await provider.gates.save(gate("gate-1", work_item_id="eligible"))

    runnable = await provider.work_items.find_runnable(
        RunnableWorkQuery(workflow_stage=WorkflowStage.IMPLEMENTATION, now=now)
    )
    active = await provider.workflow_states.list_active_leases(LeaseLookupQuery(now=now))
    expired = await provider.workflow_states.list_expired_leases(LeaseLookupQuery(now=now))
    waiting = await provider.gates.list_waiting(WaitingGateQuery(tracker_issue_number=1))

    assert [item.work_item_id for item in runnable] == ["eligible", "expired"]
    assert [record.work_item_id for record in active] == ["active"]
    assert [record.work_item_id for record in expired] == ["expired"]
    assert [gate_record.gate_id for gate_record in waiting] == ["gate-1"]


async def assert_events_are_append_only_and_query_order_is_deterministic(
    provider: PersistenceProvider,
) -> None:
    subject = EventSubject(subject_type="work_item", subject_id="work-1")
    await provider.workflow_events.append(event("event-2", time_at(2), subject=subject))
    await provider.workflow_events.append(event("event-1", time_at(1), subject=subject))
    await provider.workflow_events.append(
        event(
            "event-3",
            time_at(3),
            subject=EventSubject(subject_type="work_item", subject_id="work-2"),
            correlation_id="other",
        )
    )

    by_subject = await provider.workflow_events.list_for_subject(subject)
    by_correlation = await provider.workflow_events.list_for_correlation("corr-1")
    recent = await provider.workflow_events.list_recent(limit=2)

    assert [workflow_event.event_id for workflow_event in by_subject] == [
        "event-1",
        "event-2",
    ]
    assert [workflow_event.event_id for workflow_event in by_correlation] == [
        "event-1",
        "event-2",
    ]
    assert [workflow_event.event_id for workflow_event in recent] == ["event-2", "event-3"]


async def assert_round_tripped_datetimes_are_timezone_aware(
    provider: PersistenceProvider,
) -> None:
    await provider.projects.save(project())
    await provider.work_items.save(work_item("work-1", issue_number=9))
    await provider.workflow_states.save(
        state(
            "work-1",
            lease=Lease(worker_id="Codex-1", claimed_at=time_at(), expires_at=time_at(20)),
            blockers=(
                Blocker(
                    blocker_id="blocker-1",
                    summary="Waiting.",
                    created_at=time_at(2),
                    resolved_at=time_at(3),
                ),
            ),
        )
    )
    await provider.gates.save(gate("gate-1", work_item_id="work-1"))
    await provider.agent_runs.save(agent_run("run-1", work_item_id="work-1"))
    await provider.tool_invocations.save(tool_invocation())
    await provider.workflow_events.append(event("event-1", time_at(2)))

    stored_project = await require(provider.projects.get("project-sample"))
    stored_state = await require(provider.workflow_states.get("work-1"))
    stored_gate = await require(provider.gates.get("gate-1"))
    stored_run = await require(provider.agent_runs.get("run-1"))
    stored_invocation = await require(provider.tool_invocations.get("invocation-1"))
    stored_event = await require(provider.workflow_events.get("event-1"))

    assert_utc_aware(stored_project.created_at)
    assert_utc_aware(stored_project.updated_at)
    assert_utc_aware(stored_state.created_at)
    assert_utc_aware(stored_state.updated_at)
    assert stored_state.state.lease is not None
    assert_utc_aware(stored_state.state.lease.claimed_at)
    assert_utc_aware(stored_state.state.lease.expires_at)
    assert_utc_aware(stored_state.state.blockers[0].created_at)
    assert stored_state.state.blockers[0].resolved_at is not None
    assert_utc_aware(stored_state.state.blockers[0].resolved_at)
    assert_utc_aware(stored_gate.created_at)
    assert_utc_aware(stored_gate.updated_at)
    assert_utc_aware(stored_run.started_at)
    assert_utc_aware(stored_invocation.happened_at)
    assert_utc_aware(stored_event.happened_at)


async def require[T](awaitable: Awaitable[T | None]) -> T:
    value = await awaitable
    assert value is not None
    return value


def assert_utc_aware(value: datetime) -> None:
    assert value.tzinfo is not None
    assert value.utcoffset() == timedelta(0)


def project(project_id: str = "project-sample") -> Project:
    return Project(
        project_id=project_id,
        name="Sample Project",
        summary="Public-safe sample project.",
        created_at=time_at(),
        updated_at=time_at(),
        source_provenance=provenance(),
        public_safety=PublicSafetyClass.PUBLIC_SAFE_SAMPLE,
        redaction_status=RedactionStatus.NOT_REQUIRED,
    )


def target_repo(target_repo_id: str = "repo-sample") -> TargetRepo:
    return TargetRepo(
        target_repo_id=target_repo_id,
        provider=RepositoryProvider.GITHUB,
        owner="example-org",
        name="example-repo",
        visibility=RepositoryVisibility.PUBLIC,
        project=project_ref(),
        default_branch="main",
        created_at=time_at(),
        updated_at=time_at(),
        source_provenance=provenance(),
        public_safety=PublicSafetyClass.PUBLIC_SAFE_SAMPLE,
        redaction_status=RedactionStatus.NOT_REQUIRED,
    )


def source_connection() -> SourceConnection:
    return SourceConnection(
        source_connection_id="source-github",
        project=project_ref(),
        source_system=SourceSystem.GITHUB,
        display_name="Example GitHub",
        status=SourceConnectionStatus.ACTIVE,
        target_repo=target_repo_ref(),
        created_at=time_at(),
        updated_at=time_at(),
        source_provenance=provenance(source_system=SourceSystem.GITHUB),
        public_safety=PublicSafetyClass.PUBLIC_SAFE_SAMPLE,
        redaction_status=RedactionStatus.NOT_REQUIRED,
    )


def source_observation(observation_id: str = "observation-1") -> SourceObservation:
    return SourceObservation(
        observation_id=observation_id,
        source_connection_id="source-github",
        external_id="issue-9",
        content_hash=content_hash(),
        summary="Issue metadata summary.",
        payload_schema="github_issue_summary.v1",
        payload={"issue_number": 9},
        created_at=time_at(),
        updated_at=time_at(),
        source_provenance=provenance(source_system=SourceSystem.GITHUB),
        public_safety=PublicSafetyClass.PUBLIC_SAFE_SAMPLE,
        redaction_status=RedactionStatus.NOT_REQUIRED,
    )


def sync_cursor(cursor_id: str = "cursor-1") -> SyncCursor:
    return SyncCursor(
        cursor_id=cursor_id,
        source_connection_id="source-github",
        cursor_name="issues",
        cursor_value="cursor-value",
        created_at=time_at(),
        updated_at=time_at(),
        source_provenance=provenance(source_system=SourceSystem.GITHUB),
        public_safety=PublicSafetyClass.PUBLIC_SAFE_SAMPLE,
        redaction_status=RedactionStatus.NOT_REQUIRED,
    )


def work_item(work_item_id: str, *, issue_number: int) -> WorkItem:
    return WorkItem(
        work_item_id=work_item_id,
        item_type=WorkItemType.TASK,
        title=f"Issue {issue_number}",
        goal="Implement a public-safe sample task.",
        target_repo=target_repo_ref(),
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
        created_at=time_at(issue_number),
        updated_at=time_at(issue_number),
        source_provenance=provenance(),
        public_safety=PublicSafetyClass.PUBLIC_SAFE_SAMPLE,
        redaction_status=RedactionStatus.NOT_REQUIRED,
    )


def state(
    work_item_id: str,
    *,
    lease: Lease | None = None,
    blockers: tuple[Blocker, ...] = (),
) -> WorkflowStateRecord:
    return WorkflowStateRecord(
        work_item_id=work_item_id,
        state=WorkflowState(
            stage=WorkflowStage.IMPLEMENTATION,
            status=QueueStatus.TODO,
            review_route=ReviewRoute.REVIEW_BOTH,
            risk=RiskLevel.HIGH,
            lease=lease,
            blockers=blockers,
        ),
        created_at=time_at(),
        updated_at=time_at(),
        source_provenance=provenance(),
        public_safety=PublicSafetyClass.PUBLIC_SAFE_SAMPLE,
        redaction_status=RedactionStatus.NOT_REQUIRED,
    )


def gate(gate_id: str, *, work_item_id: str) -> ApprovalGate:
    return ApprovalGate(
        gate_id=gate_id,
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
        evidence_refs=(evidence_ref(),),
        created_at=time_at(),
        updated_at=time_at(),
        source_provenance=provenance(),
        public_safety=PublicSafetyClass.PUBLIC_SAFE_SAMPLE,
        redaction_status=RedactionStatus.NOT_REQUIRED,
    )


def agent_run(run_id: str, *, work_item_id: str) -> AgentRun:
    return AgentRun(
        run_id=run_id,
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
        started_at=time_at(),
        created_at=time_at(),
        updated_at=time_at(),
        source_provenance=provenance(),
        public_safety=PublicSafetyClass.PUBLIC_SAFE_SAMPLE,
        redaction_status=RedactionStatus.NOT_REQUIRED,
    )


def evidence_bundle(bundle_id: str, *, subject_id: str) -> EvidenceBundle:
    return EvidenceBundle(
        bundle_id=bundle_id,
        subject_type="work_item",
        subject_id=subject_id,
        refs=(evidence_ref(),),
        created_at=time_at(),
        updated_at=time_at(),
        source_provenance=provenance(),
        public_safety=PublicSafetyClass.PUBLIC_SAFE_SAMPLE,
        redaction_status=RedactionStatus.NOT_REQUIRED,
    )


def tool_connection() -> ToolConnection:
    return ToolConnection(
        tool_connection_id="tool-github",
        project=project_ref(),
        tool_type="github",
        display_name="GitHub",
        status=ToolConnectionStatus.ACTIVE,
        created_at=time_at(),
        updated_at=time_at(),
        source_provenance=provenance(),
        public_safety=PublicSafetyClass.PUBLIC_SAFE_SAMPLE,
        redaction_status=RedactionStatus.NOT_REQUIRED,
    )


def tool_policy(tool_policy_id: str = "policy-1") -> ToolPolicy:
    return ToolPolicy(
        tool_policy_id=tool_policy_id,
        project=project_ref(),
        tool_type="github",
        action_type="create_pull_request",
        decision=ToolPolicyDecision.REQUIRE_GATE,
        summary="Require gate for pull request creation.",
        created_at=time_at(),
        updated_at=time_at(),
        source_provenance=provenance(),
        public_safety=PublicSafetyClass.PUBLIC_SAFE_SAMPLE,
        redaction_status=RedactionStatus.NOT_REQUIRED,
    )


def action_request() -> ActionRequest:
    return ActionRequest(
        action_request_id="action-1",
        project=project_ref(),
        tool_type="github",
        action_type="create_pull_request",
        status=ActionRequestStatus.GATED,
        summary="Request PR creation.",
        required_gate_id="gate-1",
        created_at=time_at(),
        updated_at=time_at(),
        source_provenance=provenance(),
        public_safety=PublicSafetyClass.PUBLIC_SAFE_SAMPLE,
        redaction_status=RedactionStatus.NOT_REQUIRED,
    )


def tool_invocation() -> ToolInvocation:
    return ToolInvocation(
        tool_invocation_id="invocation-1",
        tool_type="github",
        action_type="create_pull_request",
        status=ToolInvocationStatus.SKIPPED,
        happened_at=time_at(),
        summary="Skipped until approval.",
        action_request_id="action-1",
        created_at=time_at(),
        updated_at=time_at(),
        source_provenance=provenance(),
        public_safety=PublicSafetyClass.PUBLIC_SAFE_SAMPLE,
        redaction_status=RedactionStatus.NOT_REQUIRED,
    )


def event(
    event_id: str,
    happened_at: datetime,
    *,
    subject: EventSubject | None = None,
    correlation_id: str = "corr-1",
) -> WorkflowEvent:
    return WorkflowEvent(
        event_id=event_id,
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
        source_provenance=provenance(),
        redaction_status=RedactionStatus.NOT_REQUIRED,
    )


def time_at(minutes: int = 0) -> datetime:
    return datetime(2026, 5, 25, 12, 0, tzinfo=UTC) + timedelta(minutes=minutes)


def project_ref() -> ProjectRef:
    return ProjectRef(project_id="project-sample", name="Sample Project")


def target_repo_ref() -> TargetRepoRef:
    return TargetRepoRef(
        target_repo_id="repo-sample",
        provider=RepositoryProvider.GITHUB,
        owner="example-org",
        name="example-repo",
        visibility=RepositoryVisibility.PUBLIC,
        project=project_ref(),
    )


def repo_lookup() -> RepoLookup:
    return RepoLookup(
        provider=RepositoryProvider.GITHUB,
        owner="example-org",
        name="example-repo",
    )


def provenance(source_system: SourceSystem = SourceSystem.HOISA) -> SourceProvenance:
    return SourceProvenance(
        source_system=source_system,
        source_id="source-sample",
        observed_at=time_at(),
        source_url="https://github.com/example-org/example-repo/issues/9",
        public_safety=PublicSafetyClass.PUBLIC_SAFE_SAMPLE,
    )


def content_hash() -> ContentHash:
    return ContentHash(algorithm="sha256", value="abc123")


def evidence_ref() -> EvidenceRef:
    return EvidenceRef(
        evidence_id="evidence-plan",
        kind=EvidenceKind.PLAN,
        uri="docs/agent-plans/9-sample.md",
        summary="Public-safe plan.",
        public_safety=PublicSafetyClass.PUBLIC_SAFE_SAMPLE,
        redaction_status=RedactionStatus.NOT_REQUIRED,
    )


def observation_query() -> SourceObservationQuery:
    return SourceObservationQuery(
        source_connection_id="source-github",
        external_id="issue-9",
        content_hash_value="abc123",
    )


def cursor_key() -> SyncCursorKey:
    return SyncCursorKey(source_connection_id="source-github", cursor_name="issues")


def tool_query() -> ToolActionQuery:
    return ToolActionQuery(
        project_id="project-sample",
        tool_type="github",
        action_type="create_pull_request",
    )
