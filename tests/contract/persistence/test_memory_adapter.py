import asyncio
from collections.abc import Coroutine
from datetime import UTC, datetime, timedelta
from typing import Any

from bson import ObjectId
import pytest

from hoisa.adapters.persistence.memory import InMemoryStore
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
    PersistenceConflictError,
    RepoLookup,
    RunnableWorkQuery,
    SourceObservationQuery,
    SyncCursorKey,
    ToolActionQuery,
    WaitingGateQuery,
    repo_lookup_filter,
    source_observation_filter,
    sync_cursor_filter,
)


def test_generic_store_inserts_object_ids_and_finds_records() -> None:
    store = InMemoryStore()
    project = run(store.insert(_project(None)))
    project_id = _stored_id(project)
    repo = run(store.insert(_target_repo(_id(2), project_id=project_id)))
    repo_id = _stored_id(repo)
    source = run(store.insert(_source_connection(_id(3), project_id=project_id, repo_id=repo_id)))
    source_id = _stored_id(source)
    run(store.insert(_source_observation(_id(4), source_id=source_id)))
    cursor = run(store.insert(_sync_cursor(_id(5), source_id=source_id)))
    work = run(store.insert(_work_item(_id(6), project_id=project_id, repo_id=repo_id)))
    work_id = _stored_id(work)
    run(store.insert(_state(work_id)))
    gate = run(store.insert(_gate(_id(7), work_item_id=work_id)))
    gate_id = _stored_id(gate)
    run(store.insert(_agent_run(_id(8), work_item_id=work_id)))
    run(store.insert(_evidence_bundle(_id(9), subject_id=work_id)))
    run(store.insert(_tool_connection(_id(10), project_id=project_id)))
    run(store.insert(_tool_policy(_id(11), project_id=project_id)))
    action = run(store.insert(_action_request(_id(12), project_id=project_id, gate_id=gate_id)))
    action_id = _stored_id(action)
    run(store.insert(_tool_invocation(_id(13), action_request_id=action_id)))
    event = run(store.append_event(_event(_id(14), _time(2), subject_id=work_id)))

    assert isinstance(project.id, ObjectId)
    assert project.version == 1
    assert run(store.get(Project, project_id)) == project
    assert run(store.get(TargetRepo, filter=repo_lookup_filter(_repo_lookup()))) == repo
    assert run(
        store.get(
            SourceObservation, filter=source_observation_filter(_observation_query(source_id))
        )
    )
    assert run(store.get(SyncCursor, filter=sync_cursor_filter(_cursor_key(source_id)))) == cursor
    assert run(store.get(WorkItem, filter={"tracker_issue.issue_number": 9})) == work
    assert len(run(store.find(TargetRepo, {"project.project_id": project_id}))) == 1
    assert len(run(store.list_tool_policies_for_action(_tool_query(project_id)))) == 1
    assert len(run(store.list_tool_invocations_by_action(_tool_query(project_id)))) == 1
    assert run(store.get(WorkflowEvent, event.id)) == event


def test_unique_indexes_and_append_only_events_are_rejected() -> None:
    store = InMemoryStore()
    project = run(store.insert(_project(_id(1))))
    project_id = _stored_id(project)
    repo = run(store.insert(_target_repo(_id(2), project_id=project_id)))
    repo_id = _stored_id(repo)
    source = run(store.insert(_source_connection(_id(3), project_id=project_id, repo_id=repo_id)))
    source_id = _stored_id(source)
    run(store.insert(_source_observation(_id(4), source_id=source_id)))
    run(store.insert(_sync_cursor(_id(5), source_id=source_id)))
    run(store.insert(_work_item(_id(6), project_id=project_id, repo_id=repo_id)))
    run(store.insert(_tool_policy(_id(7), project_id=project_id)))
    run(store.append_event(_event(_id(8), _time(), subject_id=_id(6))))

    with pytest.raises(DuplicateRecordError, match="target_repo"):
        run(store.insert(_target_repo(_id(20), project_id=project_id)))
    with pytest.raises(DuplicateRecordError, match="source_observation"):
        run(store.insert(_source_observation(_id(21), source_id=source_id)))
    with pytest.raises(DuplicateRecordError, match="sync_cursor"):
        run(store.insert(_sync_cursor(_id(22), source_id=source_id)))
    with pytest.raises(DuplicateRecordError, match="work_item_tracker"):
        run(store.insert(_work_item(_id(23), project_id=project_id, repo_id=repo_id)))
    with pytest.raises(DuplicateRecordError, match="tool_policy"):
        run(store.insert(_tool_policy(_id(24), project_id=project_id)))
    with pytest.raises(DuplicateRecordError, match="Workflow event"):
        run(store.append_event(_event(_id(8), _time(1), subject_id=_id(6))))


def test_save_uses_optimistic_versions() -> None:
    store = InMemoryStore()
    project = run(store.insert(_project(_id(1))))
    project_id = _stored_id(project)

    updated = run(store.save(project.model_copy(update={"summary": "Updated summary."})))
    saved_project = run(store.get(Project, project_id))

    assert updated.version == 2
    assert saved_project is not None
    assert saved_project.summary == "Updated summary."
    with pytest.raises(PersistenceConflictError):
        run(store.save(project.model_copy(update={"summary": "Stale update."})))


def test_runnable_gate_and_lease_queries_are_intention_revealing() -> None:
    store = InMemoryStore()
    project = run(store.insert(_project(_id(1))))
    project_id = _stored_id(project)
    repo = run(store.insert(_target_repo(_id(2), project_id=project_id)))
    repo_id = _stored_id(repo)
    now = _time(10)

    eligible = run(
        store.insert(_work_item(_id(3), project_id=project_id, repo_id=repo_id, issue_number=1))
    )
    active = run(
        store.insert(_work_item(_id(4), project_id=project_id, repo_id=repo_id, issue_number=2))
    )
    expired = run(
        store.insert(_work_item(_id(5), project_id=project_id, repo_id=repo_id, issue_number=3))
    )
    blocked = run(
        store.insert(_work_item(_id(6), project_id=project_id, repo_id=repo_id, issue_number=4))
    )
    eligible_id = _stored_id(eligible)
    active_id = _stored_id(active)
    expired_id = _stored_id(expired)
    blocked_id = _stored_id(blocked)
    run(store.insert(_state(eligible_id)))
    run(
        store.insert(
            _state(
                active_id,
                lease=Lease(worker_id="Codex-1", claimed_at=_time(), expires_at=_time(20)),
            )
        )
    )
    run(
        store.insert(
            _state(
                expired_id,
                lease=Lease(worker_id="Codex-2", claimed_at=_time(), expires_at=_time(5)),
            )
        )
    )
    run(
        store.insert(
            _state(
                blocked_id,
                blockers=(Blocker(blocker_id="blocker-1", summary="Waiting.", created_at=_time()),),
            )
        )
    )
    run(store.insert(_gate(_id(7), work_item_id=eligible_id)))

    runnable = run(
        store.find_runnable_work(
            RunnableWorkQuery(workflow_stage=WorkflowStage.IMPLEMENTATION, now=now)
        )
    )
    active_leases = run(store.list_active_leases(LeaseLookupQuery(now=now)))
    expired_leases = run(store.list_expired_leases(LeaseLookupQuery(now=now)))
    waiting = run(store.list_waiting_gates(WaitingGateQuery(tracker_issue_number=1)))

    assert [item.id for item in runnable] == [eligible_id, expired_id]
    assert [record.work_item_id for record in active_leases] == [active_id]
    assert [record.work_item_id for record in expired_leases] == [expired_id]
    assert [gate.work_item_id for gate in waiting] == [eligible_id]


def test_events_are_append_only_and_query_order_is_deterministic() -> None:
    store = InMemoryStore()
    subject = EventSubject(subject_type="work_item", subject_id=_id(1))
    run(store.append_event(_event(_id(2), _time(2), subject=subject)))
    run(store.append_event(_event(_id(1), _time(1), subject=subject)))
    run(
        store.append_event(
            _event(
                _id(3),
                _time(3),
                subject=EventSubject(subject_type="work_item", subject_id=_id(4)),
                correlation_id="other",
            )
        )
    )

    by_subject = run(store.list_events_for_subject(subject))
    by_correlation = run(store.list_events_for_correlation("corr-1"))
    recent = run(store.list_recent_events(limit=2))

    assert [event.id for event in by_subject] == [_id(1), _id(2)]
    assert [event.id for event in by_correlation] == [_id(1), _id(2)]
    assert [event.id for event in recent] == [_id(2), _id(3)]


def test_store_instances_do_not_share_state() -> None:
    first = InMemoryStore()
    second = InMemoryStore()
    run(first.insert(_project(_id(1))))

    assert len(run(first.find(Project))) == 1
    assert len(run(second.find(Project))) == 0


def run[T](coro: Coroutine[Any, Any, T]) -> T:
    return asyncio.run(coro)


def _stored_id(record: Any) -> ObjectId:
    assert isinstance(record.id, ObjectId)
    return record.id


def _id(number: int) -> ObjectId:
    return ObjectId(f"650000000000000000{number:06x}")


def _project(project_id: ObjectId | None = None) -> Project:
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


def _target_repo(target_repo_id: ObjectId, *, project_id: ObjectId) -> TargetRepo:
    return TargetRepo(
        id=target_repo_id,
        provider=RepositoryProvider.GITHUB,
        owner="example-org",
        name="example-repo",
        visibility=RepositoryVisibility.PUBLIC,
        project=_project_ref(project_id),
        default_branch="main",
        created_at=_time(),
        updated_at=_time(),
        source_provenance=_provenance(),
        public_safety=PublicSafetyClass.PUBLIC_SAFE_SAMPLE,
        redaction_status=RedactionStatus.NOT_REQUIRED,
    )


def _source_connection(
    source_connection_id: ObjectId, *, project_id: ObjectId, repo_id: ObjectId
) -> SourceConnection:
    return SourceConnection(
        id=source_connection_id,
        project=_project_ref(project_id),
        source_system=SourceSystem.GITHUB,
        display_name="Example GitHub",
        status=SourceConnectionStatus.ACTIVE,
        target_repo=_target_repo_ref(project_id=project_id, repo_id=repo_id),
        created_at=_time(),
        updated_at=_time(),
        source_provenance=_provenance(source_system=SourceSystem.GITHUB),
        public_safety=PublicSafetyClass.PUBLIC_SAFE_SAMPLE,
        redaction_status=RedactionStatus.NOT_REQUIRED,
    )


def _source_observation(observation_id: ObjectId, *, source_id: ObjectId) -> SourceObservation:
    return SourceObservation(
        id=observation_id,
        source_connection_id=source_id,
        external_id="issue-9",
        content_hash=_hash(),
        summary="Issue metadata summary.",
        payload_schema="github_issue_summary.v1",
        payload={"issue_number": 9, "state": "open"},
        created_at=_time(),
        updated_at=_time(),
        source_provenance=_provenance(source_system=SourceSystem.GITHUB),
        public_safety=PublicSafetyClass.PUBLIC_SAFE_SAMPLE,
        redaction_status=RedactionStatus.NOT_REQUIRED,
    )


def _sync_cursor(cursor_id: ObjectId, *, source_id: ObjectId) -> SyncCursor:
    return SyncCursor(
        id=cursor_id,
        source_connection_id=source_id,
        cursor_name="issues",
        cursor_value="2026-05-25T12:00:00Z",
        created_at=_time(),
        updated_at=_time(),
        source_provenance=_provenance(source_system=SourceSystem.GITHUB),
        public_safety=PublicSafetyClass.PUBLIC_SAFE_SAMPLE,
        redaction_status=RedactionStatus.NOT_REQUIRED,
    )


def _work_item(
    work_item_id: ObjectId,
    *,
    project_id: ObjectId,
    repo_id: ObjectId,
    issue_number: int = 9,
) -> WorkItem:
    return WorkItem(
        id=work_item_id,
        item_type=WorkItemType.TASK,
        title=f"Issue {issue_number}",
        goal="Implement a public-safe sample task.",
        target_repo=_target_repo_ref(project_id=project_id, repo_id=repo_id),
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
    work_item_id: ObjectId,
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


def _gate(gate_id: ObjectId, *, work_item_id: ObjectId) -> ApprovalGate:
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


def _agent_run(run_id: ObjectId, *, work_item_id: ObjectId) -> AgentRun:
    return AgentRun(
        id=run_id,
        work_item_id=work_item_id,
        workflow_stage=WorkflowStage.IMPLEMENTATION,
        runner_profile=_runner_profile(),
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


def _evidence_bundle(bundle_id: ObjectId, *, subject_id: ObjectId) -> EvidenceBundle:
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


def _tool_connection(connection_id: ObjectId, *, project_id: ObjectId) -> ToolConnection:
    return ToolConnection(
        id=connection_id,
        project=_project_ref(project_id),
        tool_type="github",
        display_name="GitHub",
        status=ToolConnectionStatus.ACTIVE,
        allowed_action_summaries=("read issues",),
        created_at=_time(),
        updated_at=_time(),
        source_provenance=_provenance(),
        public_safety=PublicSafetyClass.PUBLIC_SAFE_SAMPLE,
        redaction_status=RedactionStatus.NOT_REQUIRED,
    )


def _tool_policy(policy_id: ObjectId, *, project_id: ObjectId) -> ToolPolicy:
    return ToolPolicy(
        id=policy_id,
        project=_project_ref(project_id),
        tool_type="github",
        action_type="create_pull_request",
        decision=ToolPolicyDecision.REQUIRE_GATE,
        required_gate_type="merge_readiness",
        summary="Require a gate before PR creation.",
        created_at=_time(),
        updated_at=_time(),
        source_provenance=_provenance(),
        public_safety=PublicSafetyClass.PUBLIC_SAFE_SAMPLE,
        redaction_status=RedactionStatus.NOT_REQUIRED,
    )


def _action_request(
    action_request_id: ObjectId, *, project_id: ObjectId, gate_id: ObjectId
) -> ActionRequest:
    return ActionRequest(
        id=action_request_id,
        project=_project_ref(project_id),
        tool_type="github",
        action_type="create_pull_request",
        status=ActionRequestStatus.GATED,
        summary="Request to open a PR.",
        required_gate_id=gate_id,
        created_at=_time(),
        updated_at=_time(),
        source_provenance=_provenance(),
        public_safety=PublicSafetyClass.PUBLIC_SAFE_SAMPLE,
        redaction_status=RedactionStatus.NOT_REQUIRED,
    )


def _tool_invocation(invocation_id: ObjectId, *, action_request_id: ObjectId) -> ToolInvocation:
    return ToolInvocation(
        id=invocation_id,
        tool_type="github",
        action_type="create_pull_request",
        status=ToolInvocationStatus.SKIPPED,
        happened_at=_time(),
        summary="Skipped until gate approval.",
        action_request_id=action_request_id,
        created_at=_time(),
        updated_at=_time(),
        source_provenance=_provenance(),
        public_safety=PublicSafetyClass.PUBLIC_SAFE_SAMPLE,
        redaction_status=RedactionStatus.NOT_REQUIRED,
    )


def _event(
    event_id: ObjectId,
    happened_at: datetime,
    *,
    subject: EventSubject | None = None,
    subject_id: ObjectId | None = None,
    correlation_id: str = "corr-1",
) -> WorkflowEvent:
    return WorkflowEvent(
        id=event_id,
        event_type=WorkflowEventType.WORK_ITEM_SELECTED,
        happened_at=happened_at,
        actor=ActorRef(actor_type=ActorType.AGENT, actor_id="codex"),
        subject=subject or EventSubject(subject_type="work_item", subject_id=subject_id or _id(6)),
        correlation_id=correlation_id,
        workflow_stage=WorkflowStage.IMPLEMENTATION,
        risk=RiskLevel.HIGH,
        public_safety=PublicSafetyClass.PUBLIC_SAFE_SAMPLE,
        payload_schema="work_selection.v1",
        payload={"selected": True},
        evidence_refs=(_evidence_ref(),),
        source_provenance=_provenance(),
        redaction_status=RedactionStatus.NOT_REQUIRED,
        created_at=_time(),
        updated_at=_time(),
    )


def _time(minutes: int = 0) -> datetime:
    return datetime(2026, 5, 25, 12, 0, tzinfo=UTC) + timedelta(minutes=minutes)


def _project_ref(project_id: ObjectId) -> ProjectRef:
    return ProjectRef(project_id=project_id, name="Sample Project")


def _target_repo_ref(*, project_id: ObjectId, repo_id: ObjectId) -> TargetRepoRef:
    return TargetRepoRef(
        target_repo_id=repo_id,
        provider=RepositoryProvider.GITHUB,
        owner="example-org",
        name="example-repo",
        visibility=RepositoryVisibility.PUBLIC,
        project=_project_ref(project_id),
    )


def _repo_lookup() -> RepoLookup:
    return RepoLookup(
        provider=RepositoryProvider.GITHUB,
        owner="example-org",
        name="example-repo",
    )


def _observation_query(source_id: ObjectId) -> SourceObservationQuery:
    return SourceObservationQuery(
        source_connection_id=source_id,
        external_id="issue-9",
        content_hash_value="abc123",
    )


def _cursor_key(source_id: ObjectId) -> SyncCursorKey:
    return SyncCursorKey(source_connection_id=source_id, cursor_name="issues")


def _tool_query(project_id: ObjectId) -> ToolActionQuery:
    return ToolActionQuery(
        project_id=project_id,
        tool_type="github",
        action_type="create_pull_request",
    )


def _evidence_ref() -> EvidenceRef:
    return EvidenceRef(
        evidence_id="evidence-plan",
        kind=EvidenceKind.PLAN,
        uri="docs/agent-plans/sample.md",
        summary="Public-safe plan.",
        public_safety=PublicSafetyClass.PUBLIC_SAFE_SAMPLE,
        redaction_status=RedactionStatus.NOT_REQUIRED,
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


def _runner_profile() -> RunnerProfile:
    return RunnerProfile(
        runner_type="codex",
        profile_name="local-sandbox",
        sandbox="workspace",
        network_access=False,
    )
