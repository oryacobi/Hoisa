from collections.abc import Awaitable
from datetime import UTC, datetime, timedelta
import hashlib

from bson import ObjectId
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
from hoisa.domain.models import BsonObjectId
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


def object_id(value: str | BsonObjectId) -> BsonObjectId:
    if isinstance(value, ObjectId):
        return value
    return ObjectId(hashlib.sha256(value.encode("utf-8")).hexdigest()[:24])


async def assert_repositories_save_and_fetch_current_state_records(
    provider: PersistenceProvider,
) -> None:
    await provider.catalog.save_project(project())
    await provider.catalog.save_target_repo(target_repo())
    await provider.sources.save_connection(source_connection())
    await provider.sources.save_observation(source_observation())
    await provider.sources.save_cursor(sync_cursor())
    await provider.workflow.save_work_item(work_item("work-1", issue_number=9))
    await provider.workflow.save_state(state("work-1"))
    await provider.workflow.save_gate(gate("gate-1", work_item_id="work-1"))
    await provider.workflow.save_agent_run(agent_run("run-1", work_item_id="work-1"))
    await provider.evidence.save_bundle(evidence_bundle("bundle-1", subject_id="work-1"))
    await provider.tools.save_connection(tool_connection())
    await provider.tools.save_policy(tool_policy())
    await provider.tools.save_action_request(action_request())
    await provider.tools.save_invocation(tool_invocation())
    await provider.events.append(event("event-1", time_at(2)))

    assert await provider.catalog.get_project(object_id("project-sample")) is not None
    assert await provider.catalog.get_target_repo(object_id("repo-sample")) is not None
    assert await provider.catalog.get_target_repo_by_provider(repo_lookup()) is not None
    assert len(await provider.catalog.list_target_repos(object_id("project-sample"))) == 1
    assert await provider.sources.get_connection(object_id("source-github")) is not None
    assert len(await provider.sources.find_observations(observation_query())) == 1
    assert await provider.sources.get_cursor(cursor_key()) is not None
    assert await provider.workflow.find_work_item_by_tracker_issue(
        provider="github", issue_number=9
    )
    assert await provider.workflow.get_state(object_id("work-1")) is not None
    assert len(await provider.workflow.list_gates(object_id("work-1"))) == 1
    assert len(await provider.workflow.list_agent_runs(object_id("work-1"))) == 1
    assert (
        len(
            await provider.evidence.list_bundles(
                subject_type="work_item",
                subject_id=object_id("work-1"),
            )
        )
        == 1
    )
    assert len(await provider.tools.list_connections(object_id("project-sample"))) == 1
    assert len(await provider.tools.find_policies(tool_query())) == 1
    assert len(await provider.tools.list_action_requests_by_status(ActionRequestStatus.GATED)) == 1
    assert len(await provider.tools.list_action_requests_for_gate(object_id("gate-1"))) == 1
    assert len(await provider.tools.list_invocations_for_action_request(object_id("action-1"))) == 1
    assert len(await provider.tools.list_invocations_by_tool_action(tool_query())) == 1
    assert await provider.events.get(object_id("event-1")) is not None


async def assert_unique_keys_are_rejected_deterministically(
    provider: PersistenceProvider,
) -> None:
    await provider.catalog.save_target_repo(target_repo("repo-1"))
    await provider.sources.save_observation(source_observation("observation-1"))
    await provider.sources.save_cursor(sync_cursor("cursor-1"))
    await provider.workflow.save_work_item(work_item("work-1", issue_number=9))
    await provider.tools.save_policy(tool_policy("policy-1"))
    await provider.events.append(event("event-1", time_at()))

    with pytest.raises(DuplicateRecordError, match="target repository"):
        await provider.catalog.save_target_repo(target_repo("repo-2"))
    with pytest.raises(DuplicateRecordError, match="source observation"):
        await provider.sources.save_observation(source_observation("observation-2"))
    with pytest.raises(DuplicateRecordError, match="sync cursor"):
        await provider.sources.save_cursor(sync_cursor("cursor-2"))
    with pytest.raises(DuplicateRecordError, match="tracker issue"):
        await provider.workflow.save_work_item(work_item("work-2", issue_number=9))
    with pytest.raises(DuplicateRecordError, match="tool policy"):
        await provider.tools.save_policy(tool_policy("policy-2"))
    with pytest.raises(DuplicateRecordError, match="Workflow event"):
        await provider.events.append(event("event-1", time_at(1)))


async def assert_runnable_gate_and_lease_queries_are_intention_revealing(
    provider: PersistenceProvider,
) -> None:
    now = time_at(10)
    await provider.workflow.save_work_item(work_item("eligible", issue_number=1))
    await provider.workflow.save_work_item(work_item("active", issue_number=2))
    await provider.workflow.save_work_item(work_item("expired", issue_number=3))
    await provider.workflow.save_work_item(work_item("blocked", issue_number=4))
    await provider.workflow.save_state(state("eligible"))
    await provider.workflow.save_state(
        state(
            "active",
            lease=Lease(worker_id="Codex-1", claimed_at=time_at(), expires_at=time_at(20)),
        )
    )
    await provider.workflow.save_state(
        state(
            "expired",
            lease=Lease(worker_id="Codex-2", claimed_at=time_at(), expires_at=time_at(5)),
        )
    )
    await provider.workflow.save_state(
        state(
            "blocked",
            blockers=(Blocker(blocker_id="blocker-1", summary="Waiting.", created_at=time_at()),),
        )
    )
    await provider.workflow.save_gate(gate("gate-1", work_item_id="eligible"))

    runnable = await provider.workflow.find_runnable_work(
        RunnableWorkQuery(workflow_stage=WorkflowStage.IMPLEMENTATION, now=now)
    )
    active = await provider.workflow.list_active_leases(LeaseLookupQuery(now=now))
    expired = await provider.workflow.list_expired_leases(LeaseLookupQuery(now=now))
    waiting = await provider.workflow.list_waiting_gates(WaitingGateQuery(tracker_issue_number=1))

    assert [item.id for item in runnable] == [object_id("eligible"), object_id("expired")]
    assert [record.work_item_id for record in active] == [object_id("active")]
    assert [record.work_item_id for record in expired] == [object_id("expired")]
    assert [gate_record.id for gate_record in waiting] == [object_id("gate-1")]


async def assert_events_are_append_only_and_query_order_is_deterministic(
    provider: PersistenceProvider,
) -> None:
    subject = EventSubject(subject_type="work_item", subject_id=object_id("work-1"))
    await provider.events.append(event("event-2", time_at(2), subject=subject))
    await provider.events.append(event("event-1", time_at(1), subject=subject))
    await provider.events.append(
        event(
            "event-3",
            time_at(3),
            subject=EventSubject(subject_type="work_item", subject_id=object_id("work-2")),
            correlation_id="other",
        )
    )

    by_subject = await provider.events.list_for_subject(subject)
    by_correlation = await provider.events.list_for_correlation("corr-1")
    recent = await provider.events.list_recent(limit=2)

    assert [workflow_event.id for workflow_event in by_subject] == [
        object_id("event-1"),
        object_id("event-2"),
    ]
    assert [workflow_event.id for workflow_event in by_correlation] == [
        object_id("event-1"),
        object_id("event-2"),
    ]
    assert [workflow_event.id for workflow_event in recent] == [
        object_id("event-2"),
        object_id("event-3"),
    ]


async def assert_round_tripped_datetimes_are_timezone_aware(
    provider: PersistenceProvider,
) -> None:
    await provider.catalog.save_project(project())
    await provider.workflow.save_work_item(work_item("work-1", issue_number=9))
    await provider.workflow.save_state(
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
    await provider.workflow.save_gate(gate("gate-1", work_item_id="work-1"))
    await provider.workflow.save_agent_run(agent_run("run-1", work_item_id="work-1"))
    await provider.tools.save_invocation(tool_invocation())
    await provider.events.append(event("event-1", time_at(2)))

    stored_project = await require(provider.catalog.get_project(object_id("project-sample")))
    stored_state = await require(provider.workflow.get_state(object_id("work-1")))
    stored_gate = await require(provider.workflow.get_gate(object_id("gate-1")))
    stored_run = await require(provider.workflow.get_agent_run(object_id("run-1")))
    stored_invocation = await require(provider.tools.get_invocation(object_id("invocation-1")))
    stored_event = await require(provider.events.get(object_id("event-1")))

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


def project(project_id: str | BsonObjectId = "project-sample") -> Project:
    return Project(
        id=object_id(project_id),
        name="Sample Project",
        summary="Public-safe sample project.",
        created_at=time_at(),
        updated_at=time_at(),
        source_provenance=provenance(),
        public_safety=PublicSafetyClass.PUBLIC_SAFE_SAMPLE,
        redaction_status=RedactionStatus.NOT_REQUIRED,
    )


def target_repo(target_repo_id: str | BsonObjectId = "repo-sample") -> TargetRepo:
    return TargetRepo(
        id=object_id(target_repo_id),
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
        id=object_id("source-github"),
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


def source_observation(observation_id: str | BsonObjectId = "observation-1") -> SourceObservation:
    return SourceObservation(
        id=object_id(observation_id),
        source_connection_id=object_id("source-github"),
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


def sync_cursor(cursor_id: str | BsonObjectId = "cursor-1") -> SyncCursor:
    return SyncCursor(
        id=object_id(cursor_id),
        source_connection_id=object_id("source-github"),
        cursor_name="issues",
        cursor_value="cursor-value",
        created_at=time_at(),
        updated_at=time_at(),
        source_provenance=provenance(source_system=SourceSystem.GITHUB),
        public_safety=PublicSafetyClass.PUBLIC_SAFE_SAMPLE,
        redaction_status=RedactionStatus.NOT_REQUIRED,
    )


def work_item(work_item_id: str | BsonObjectId, *, issue_number: int) -> WorkItem:
    return WorkItem(
        id=object_id(work_item_id),
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
    work_item_id: str | BsonObjectId,
    *,
    lease: Lease | None = None,
    blockers: tuple[Blocker, ...] = (),
) -> WorkflowStateRecord:
    return WorkflowStateRecord(
        id=object_id(work_item_id),
        work_item_id=object_id(work_item_id),
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


def gate(gate_id: str | BsonObjectId, *, work_item_id: str | BsonObjectId) -> ApprovalGate:
    return ApprovalGate(
        id=object_id(gate_id),
        gate_type=GateType.PLAN_APPROVAL,
        gate_status=GateStatus.WAITING,
        work_item_id=object_id(work_item_id),
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


def agent_run(run_id: str | BsonObjectId, *, work_item_id: str | BsonObjectId) -> AgentRun:
    return AgentRun(
        id=object_id(run_id),
        work_item_id=object_id(work_item_id),
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


def evidence_bundle(
    bundle_id: str | BsonObjectId, *, subject_id: str | BsonObjectId
) -> EvidenceBundle:
    return EvidenceBundle(
        id=object_id(bundle_id),
        subject_type="work_item",
        subject_id=object_id(subject_id),
        refs=(evidence_ref(),),
        created_at=time_at(),
        updated_at=time_at(),
        source_provenance=provenance(),
        public_safety=PublicSafetyClass.PUBLIC_SAFE_SAMPLE,
        redaction_status=RedactionStatus.NOT_REQUIRED,
    )


def tool_connection() -> ToolConnection:
    return ToolConnection(
        id=object_id("tool-github"),
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


def tool_policy(tool_policy_id: str | BsonObjectId = "policy-1") -> ToolPolicy:
    return ToolPolicy(
        id=object_id(tool_policy_id),
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
        id=object_id("action-1"),
        project=project_ref(),
        tool_type="github",
        action_type="create_pull_request",
        status=ActionRequestStatus.GATED,
        summary="Request PR creation.",
        required_gate_id=object_id("gate-1"),
        created_at=time_at(),
        updated_at=time_at(),
        source_provenance=provenance(),
        public_safety=PublicSafetyClass.PUBLIC_SAFE_SAMPLE,
        redaction_status=RedactionStatus.NOT_REQUIRED,
    )


def tool_invocation() -> ToolInvocation:
    return ToolInvocation(
        id=object_id("invocation-1"),
        tool_type="github",
        action_type="create_pull_request",
        status=ToolInvocationStatus.SKIPPED,
        happened_at=time_at(),
        summary="Skipped until approval.",
        action_request_id=object_id("action-1"),
        created_at=time_at(),
        updated_at=time_at(),
        source_provenance=provenance(),
        public_safety=PublicSafetyClass.PUBLIC_SAFE_SAMPLE,
        redaction_status=RedactionStatus.NOT_REQUIRED,
    )


def event(
    event_id: str | BsonObjectId,
    happened_at: datetime,
    *,
    subject: EventSubject | None = None,
    correlation_id: str = "corr-1",
) -> WorkflowEvent:
    return WorkflowEvent(
        id=object_id(event_id),
        event_type=WorkflowEventType.WORK_ITEM_SELECTED,
        happened_at=happened_at,
        actor=ActorRef(actor_type=ActorType.AGENT, actor_id="codex"),
        subject=subject or EventSubject(subject_type="work_item", subject_id=object_id("work-1")),
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
    return ProjectRef(id=object_id("project-sample"), name="Sample Project")


def target_repo_ref() -> TargetRepoRef:
    return TargetRepoRef(
        id=object_id("repo-sample"),
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
        source_connection_id=object_id("source-github"),
        external_id="issue-9",
        content_hash_value="abc123",
    )


def cursor_key() -> SyncCursorKey:
    return SyncCursorKey(source_connection_id=object_id("source-github"), cursor_name="issues")


def tool_query() -> ToolActionQuery:
    return ToolActionQuery(
        project_id=object_id("project-sample"),
        tool_type="github",
        action_type="create_pull_request",
    )
