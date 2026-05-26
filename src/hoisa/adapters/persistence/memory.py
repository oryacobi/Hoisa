"""Deterministic in-memory persistence adapter for Hoisa tests."""

from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field

from hoisa.domain.events import EventSubject, WorkflowEvent
from hoisa.domain.evidence import EvidenceBundle
from hoisa.domain.gates import ApprovalGate, GateStatus
from hoisa.domain.models import BsonObjectId
from hoisa.domain.runs import AgentRun
from hoisa.domain.sources import SourceConnection, SourceObservation, SyncCursor
from hoisa.domain.target_repos import Project, TargetRepo
from hoisa.domain.tool_control import (
    ActionRequest,
    ActionRequestStatus,
    ToolConnection,
    ToolInvocation,
    ToolInvocationStatus,
    ToolPolicy,
)
from hoisa.domain.work_items import WorkItem
from hoisa.domain.workflow_state import Blocker, WorkflowStateRecord
from hoisa.ports.persistence import (
    ActionRequestRepository,
    AgentRunRepository,
    ApprovalGateRepository,
    DuplicateRecordError,
    EvidenceBundleRepository,
    LeaseLookupQuery,
    PersistenceProvider,
    ProjectRepository,
    RepoLookup,
    RunnableWorkQuery,
    SourceConnectionRepository,
    SourceObservationQuery,
    SourceObservationRepository,
    SyncCursorKey,
    SyncCursorRepository,
    TargetRepoRepository,
    ToolActionQuery,
    ToolConnectionRepository,
    ToolInvocationRepository,
    ToolPolicyRepository,
    WaitingGateQuery,
    WorkflowEventStore,
    WorkflowStateRepository,
    WorkItemRepository,
)


@dataclass(slots=True)
class _MemoryStore:
    projects: dict[BsonObjectId, Project] = field(default_factory=dict)
    target_repos: dict[BsonObjectId, TargetRepo] = field(default_factory=dict)
    source_connections: dict[BsonObjectId, SourceConnection] = field(default_factory=dict)
    source_observations: dict[BsonObjectId, SourceObservation] = field(default_factory=dict)
    sync_cursors: dict[BsonObjectId, SyncCursor] = field(default_factory=dict)
    work_items: dict[BsonObjectId, WorkItem] = field(default_factory=dict)
    workflow_states: dict[BsonObjectId, WorkflowStateRecord] = field(default_factory=dict)
    gates: dict[BsonObjectId, ApprovalGate] = field(default_factory=dict)
    agent_runs: dict[BsonObjectId, AgentRun] = field(default_factory=dict)
    evidence_bundles: dict[BsonObjectId, EvidenceBundle] = field(default_factory=dict)
    tool_connections: dict[BsonObjectId, ToolConnection] = field(default_factory=dict)
    tool_policies: dict[BsonObjectId, ToolPolicy] = field(default_factory=dict)
    action_requests: dict[BsonObjectId, ActionRequest] = field(default_factory=dict)
    tool_invocations: dict[BsonObjectId, ToolInvocation] = field(default_factory=dict)
    workflow_events: dict[BsonObjectId, WorkflowEvent] = field(default_factory=dict)
    workflow_event_order: list[BsonObjectId] = field(default_factory=list)


class InMemoryPersistenceProvider(PersistenceProvider):
    """In-memory implementation of all persistence repositories."""

    def __init__(self) -> None:
        self._store = _MemoryStore()
        self._projects = _InMemoryProjectRepository(self._store)
        self._target_repos = _InMemoryTargetRepoRepository(self._store)
        self._source_connections = _InMemorySourceConnectionRepository(self._store)
        self._source_observations = _InMemorySourceObservationRepository(self._store)
        self._sync_cursors = _InMemorySyncCursorRepository(self._store)
        self._work_items = _InMemoryWorkItemRepository(self._store)
        self._workflow_states = _InMemoryWorkflowStateRepository(self._store)
        self._gates = _InMemoryApprovalGateRepository(self._store)
        self._agent_runs = _InMemoryAgentRunRepository(self._store)
        self._evidence_bundles = _InMemoryEvidenceBundleRepository(self._store)
        self._tool_connections = _InMemoryToolConnectionRepository(self._store)
        self._tool_policies = _InMemoryToolPolicyRepository(self._store)
        self._action_requests = _InMemoryActionRequestRepository(self._store)
        self._tool_invocations = _InMemoryToolInvocationRepository(self._store)
        self._workflow_events = _InMemoryWorkflowEventStore(self._store)

    @property
    def projects(self) -> ProjectRepository:
        """Return the project repository."""

        return self._projects

    @property
    def target_repos(self) -> TargetRepoRepository:
        """Return the target repository repository."""

        return self._target_repos

    @property
    def source_connections(self) -> SourceConnectionRepository:
        """Return the source connection repository."""

        return self._source_connections

    @property
    def source_observations(self) -> SourceObservationRepository:
        """Return the source observation repository."""

        return self._source_observations

    @property
    def sync_cursors(self) -> SyncCursorRepository:
        """Return the sync cursor repository."""

        return self._sync_cursors

    @property
    def work_items(self) -> WorkItemRepository:
        """Return the work item repository."""

        return self._work_items

    @property
    def workflow_states(self) -> WorkflowStateRepository:
        """Return the workflow state repository."""

        return self._workflow_states

    @property
    def gates(self) -> ApprovalGateRepository:
        """Return the approval gate repository."""

        return self._gates

    @property
    def agent_runs(self) -> AgentRunRepository:
        """Return the agent run repository."""

        return self._agent_runs

    @property
    def evidence_bundles(self) -> EvidenceBundleRepository:
        """Return the evidence bundle repository."""

        return self._evidence_bundles

    @property
    def tool_connections(self) -> ToolConnectionRepository:
        """Return the tool connection repository."""

        return self._tool_connections

    @property
    def tool_policies(self) -> ToolPolicyRepository:
        """Return the tool policy repository."""

        return self._tool_policies

    @property
    def action_requests(self) -> ActionRequestRepository:
        """Return the action request repository."""

        return self._action_requests

    @property
    def tool_invocations(self) -> ToolInvocationRepository:
        """Return the tool invocation repository."""

        return self._tool_invocations

    @property
    def workflow_events(self) -> WorkflowEventStore:
        """Return the workflow event store."""

        return self._workflow_events


class _InMemoryProjectRepository:
    def __init__(self, store: _MemoryStore) -> None:
        self._store = store

    async def save(self, project: Project) -> None:
        self._store.projects[project.id] = project

    async def get(self, project_id: BsonObjectId) -> Project | None:
        return self._store.projects.get(project_id)

    async def list_all(self) -> Sequence[Project]:
        return _sorted_by_id(self._store.projects.values(), lambda project: project.id)


class _InMemoryTargetRepoRepository:
    def __init__(self, store: _MemoryStore) -> None:
        self._store = store

    async def save(self, target_repo: TargetRepo) -> None:
        _reject_collision(
            ((repo.id, _target_repo_key(repo)) for repo in self._store.target_repos.values()),
            new_id=target_repo.id,
            new_key=_target_repo_key(target_repo),
            label="target repository provider identity",
        )
        self._store.target_repos[target_repo.id] = target_repo

    async def get(self, target_repo_id: BsonObjectId) -> TargetRepo | None:
        return self._store.target_repos.get(target_repo_id)

    async def get_by_provider(self, lookup: RepoLookup) -> TargetRepo | None:
        key = (lookup.provider.value, lookup.owner, lookup.name)
        for repo in self._store.target_repos.values():
            if _target_repo_key(repo) == key:
                return repo
        return None

    async def list_by_project(self, project_id: BsonObjectId) -> Sequence[TargetRepo]:
        return _sorted_by_id(
            (repo for repo in self._store.target_repos.values() if repo.project.id == project_id),
            lambda repo: repo.id,
        )


class _InMemorySourceConnectionRepository:
    def __init__(self, store: _MemoryStore) -> None:
        self._store = store

    async def save(self, connection: SourceConnection) -> None:
        self._store.source_connections[connection.id] = connection

    async def get(self, source_connection_id: BsonObjectId) -> SourceConnection | None:
        return self._store.source_connections.get(source_connection_id)

    async def list_by_project(self, project_id: BsonObjectId) -> Sequence[SourceConnection]:
        return _sorted_by_id(
            (
                connection
                for connection in self._store.source_connections.values()
                if connection.project.id == project_id
            ),
            lambda connection: connection.id,
        )


class _InMemorySourceObservationRepository:
    def __init__(self, store: _MemoryStore) -> None:
        self._store = store

    async def save(self, observation: SourceObservation) -> None:
        _reject_collision(
            (
                (existing.id, _source_observation_key(existing))
                for existing in self._store.source_observations.values()
            ),
            new_id=observation.id,
            new_key=_source_observation_key(observation),
            label="source observation external identity",
        )
        self._store.source_observations[observation.id] = observation

    async def get(self, observation_id: BsonObjectId) -> SourceObservation | None:
        return self._store.source_observations.get(observation_id)

    async def find_by_source(self, query: SourceObservationQuery) -> Sequence[SourceObservation]:
        return _sorted_by_id(
            (
                observation
                for observation in self._store.source_observations.values()
                if _matches_observation_query(observation, query)
            ),
            lambda observation: observation.id,
        )


class _InMemorySyncCursorRepository:
    def __init__(self, store: _MemoryStore) -> None:
        self._store = store

    async def save(self, cursor: SyncCursor) -> None:
        _reject_collision(
            (
                (existing.id, _sync_cursor_key(existing))
                for existing in self._store.sync_cursors.values()
            ),
            new_id=cursor.id,
            new_key=_sync_cursor_key(cursor),
            label="sync cursor source/name",
        )
        self._store.sync_cursors[cursor.id] = cursor

    async def get(self, key: SyncCursorKey) -> SyncCursor | None:
        target = (key.source_connection_id, key.cursor_name)
        for cursor in self._store.sync_cursors.values():
            if _sync_cursor_key(cursor) == target:
                return cursor
        return None

    async def list_by_source(self, source_connection_id: BsonObjectId) -> Sequence[SyncCursor]:
        return _sorted_by_id(
            (
                cursor
                for cursor in self._store.sync_cursors.values()
                if cursor.source_connection_id == source_connection_id
            ),
            lambda cursor: cursor.id,
        )


class _InMemoryWorkItemRepository:
    def __init__(self, store: _MemoryStore) -> None:
        self._store = store

    async def save(self, work_item: WorkItem) -> None:
        if work_item.tracker_issue is not None:
            _reject_collision(
                (
                    (existing.id, _tracker_issue_key(existing))
                    for existing in self._store.work_items.values()
                    if existing.tracker_issue is not None
                ),
                new_id=work_item.id,
                new_key=_tracker_issue_key(work_item),
                label="work item tracker issue",
            )
        self._store.work_items[work_item.id] = work_item

    async def get(self, work_item_id: BsonObjectId) -> WorkItem | None:
        return self._store.work_items.get(work_item_id)

    async def find_by_tracker_issue(self, *, provider: str, issue_number: int) -> WorkItem | None:
        for work_item in self._store.work_items.values():
            if (
                work_item.tracker_issue is not None
                and work_item.tracker_issue.provider == provider
                and work_item.tracker_issue.issue_number == issue_number
            ):
                return work_item
        return None

    async def find_runnable(self, query: RunnableWorkQuery) -> Sequence[WorkItem]:
        return _sorted_work_items(
            work_item
            for work_item in self._store.work_items.values()
            if _is_runnable(work_item, self._store.workflow_states.get(work_item.id), query)
        )


class _InMemoryWorkflowStateRepository:
    def __init__(self, store: _MemoryStore) -> None:
        self._store = store

    async def save(self, state_record: WorkflowStateRecord) -> None:
        self._store.workflow_states[state_record.work_item_id] = state_record.model_copy(
            update={"id": state_record.work_item_id}
        )

    async def get(self, work_item_id: BsonObjectId) -> WorkflowStateRecord | None:
        return self._store.workflow_states.get(work_item_id)

    async def list_by_worker(self, query: LeaseLookupQuery) -> Sequence[WorkflowStateRecord]:
        return _sorted_state_records(
            record
            for record in self._store.workflow_states.values()
            if record.state.lease is not None
            and (not query.worker_id or record.state.lease.worker_id == query.worker_id)
        )

    async def list_active_leases(self, query: LeaseLookupQuery) -> Sequence[WorkflowStateRecord]:
        return _sorted_state_records(
            record
            for record in self._store.workflow_states.values()
            if record.state.lease is not None
            and (not query.worker_id or record.state.lease.worker_id == query.worker_id)
            and (query.now is None or record.state.lease.expires_at > query.now)
        )

    async def list_expired_leases(self, query: LeaseLookupQuery) -> Sequence[WorkflowStateRecord]:
        if query.now is None:
            return ()
        return _sorted_state_records(
            record
            for record in self._store.workflow_states.values()
            if record.state.lease is not None
            and (not query.worker_id or record.state.lease.worker_id == query.worker_id)
            and record.state.lease.expires_at <= query.now
        )


class _InMemoryApprovalGateRepository:
    def __init__(self, store: _MemoryStore) -> None:
        self._store = store

    async def save(self, gate: ApprovalGate) -> None:
        self._store.gates[gate.id] = gate

    async def get(self, gate_id: BsonObjectId) -> ApprovalGate | None:
        return self._store.gates.get(gate_id)

    async def list_by_work_item(self, work_item_id: BsonObjectId) -> Sequence[ApprovalGate]:
        return _sorted_gates(
            gate for gate in self._store.gates.values() if gate.work_item_id == work_item_id
        )

    async def list_waiting(self, query: WaitingGateQuery) -> Sequence[ApprovalGate]:
        return _sorted_gates(
            gate
            for gate in self._store.gates.values()
            if gate.gate_status == GateStatus.WAITING
            and _matches_waiting_gate(gate, query, self._store)
        )


class _InMemoryAgentRunRepository:
    def __init__(self, store: _MemoryStore) -> None:
        self._store = store

    async def save(self, run: AgentRun) -> None:
        self._store.agent_runs[run.id] = run

    async def get(self, run_id: BsonObjectId) -> AgentRun | None:
        return self._store.agent_runs.get(run_id)

    async def list_by_work_item(self, work_item_id: BsonObjectId) -> Sequence[AgentRun]:
        return _sorted_by_id(
            (run for run in self._store.agent_runs.values() if run.work_item_id == work_item_id),
            lambda run: run.id,
        )


class _InMemoryEvidenceBundleRepository:
    def __init__(self, store: _MemoryStore) -> None:
        self._store = store

    async def save(self, bundle: EvidenceBundle) -> None:
        self._store.evidence_bundles[bundle.id] = bundle

    async def get(self, bundle_id: BsonObjectId) -> EvidenceBundle | None:
        return self._store.evidence_bundles.get(bundle_id)

    async def list_by_subject(
        self, *, subject_type: str, subject_id: BsonObjectId
    ) -> Sequence[EvidenceBundle]:
        return _sorted_by_id(
            (
                bundle
                for bundle in self._store.evidence_bundles.values()
                if bundle.subject_type == subject_type and bundle.subject_id == subject_id
            ),
            lambda bundle: bundle.id,
        )


class _InMemoryToolConnectionRepository:
    def __init__(self, store: _MemoryStore) -> None:
        self._store = store

    async def save(self, connection: ToolConnection) -> None:
        self._store.tool_connections[connection.id] = connection

    async def get(self, tool_connection_id: BsonObjectId) -> ToolConnection | None:
        return self._store.tool_connections.get(tool_connection_id)

    async def list_by_project(self, project_id: BsonObjectId) -> Sequence[ToolConnection]:
        return _sorted_by_id(
            (
                connection
                for connection in self._store.tool_connections.values()
                if connection.project.id == project_id
            ),
            lambda connection: connection.id,
        )


class _InMemoryToolPolicyRepository:
    def __init__(self, store: _MemoryStore) -> None:
        self._store = store

    async def save(self, policy: ToolPolicy) -> None:
        _reject_collision(
            (
                (existing.id, _tool_policy_key(existing))
                for existing in self._store.tool_policies.values()
            ),
            new_id=policy.id,
            new_key=_tool_policy_key(policy),
            label="tool policy action identity",
        )
        self._store.tool_policies[policy.id] = policy

    async def get(self, tool_policy_id: BsonObjectId) -> ToolPolicy | None:
        return self._store.tool_policies.get(tool_policy_id)

    async def find_for_action(self, query: ToolActionQuery) -> Sequence[ToolPolicy]:
        return _sorted_by_id(
            (
                policy
                for policy in self._store.tool_policies.values()
                if _matches_tool_action(
                    policy.project.id,
                    policy.tool_type,
                    policy.action_type,
                    query,
                )
            ),
            lambda policy: policy.id,
        )


class _InMemoryActionRequestRepository:
    def __init__(self, store: _MemoryStore) -> None:
        self._store = store

    async def save(self, request: ActionRequest) -> None:
        self._store.action_requests[request.id] = request

    async def get(self, action_request_id: BsonObjectId) -> ActionRequest | None:
        return self._store.action_requests.get(action_request_id)

    async def list_by_status(self, status: ActionRequestStatus) -> Sequence[ActionRequest]:
        return _sorted_by_id(
            (
                request
                for request in self._store.action_requests.values()
                if request.status == status
            ),
            lambda request: request.id,
        )

    async def list_for_gate(self, gate_id: BsonObjectId) -> Sequence[ActionRequest]:
        return _sorted_by_id(
            (
                request
                for request in self._store.action_requests.values()
                if request.required_gate_id == gate_id
            ),
            lambda request: request.id,
        )


class _InMemoryToolInvocationRepository:
    def __init__(self, store: _MemoryStore) -> None:
        self._store = store

    async def save(self, invocation: ToolInvocation) -> None:
        self._store.tool_invocations[invocation.id] = invocation

    async def get(self, tool_invocation_id: BsonObjectId) -> ToolInvocation | None:
        return self._store.tool_invocations.get(tool_invocation_id)

    async def list_for_action_request(
        self, action_request_id: BsonObjectId
    ) -> Sequence[ToolInvocation]:
        return _sorted_invocations(
            invocation
            for invocation in self._store.tool_invocations.values()
            if invocation.action_request_id == action_request_id
        )

    async def list_by_tool_action(
        self,
        query: ToolActionQuery,
        *,
        status: ToolInvocationStatus | None = None,
    ) -> Sequence[ToolInvocation]:
        return _sorted_invocations(
            invocation
            for invocation in self._store.tool_invocations.values()
            if _matches_tool_action(
                _invocation_project_id(invocation, self._store),
                invocation.tool_type,
                invocation.action_type,
                query,
            )
            and (status is None or invocation.status == status)
        )


class _InMemoryWorkflowEventStore:
    def __init__(self, store: _MemoryStore) -> None:
        self._store = store

    async def append(self, event: WorkflowEvent) -> None:
        if event.id in self._store.workflow_events:
            raise DuplicateRecordError(f"Workflow event already exists: {event.id}")
        self._store.workflow_events[event.id] = event
        self._store.workflow_event_order.append(event.id)

    async def get(self, event_id: BsonObjectId) -> WorkflowEvent | None:
        return self._store.workflow_events.get(event_id)

    async def list_for_subject(self, subject: EventSubject) -> Sequence[WorkflowEvent]:
        return _sorted_events(
            event for event in self._store.workflow_events.values() if event.subject == subject
        )

    async def list_for_correlation(self, correlation_id: str) -> Sequence[WorkflowEvent]:
        return _sorted_events(
            event
            for event in self._store.workflow_events.values()
            if event.correlation_id == correlation_id
        )

    async def list_recent(self, *, limit: int) -> Sequence[WorkflowEvent]:
        if limit <= 0:
            return ()
        ordered = _sorted_events(self._store.workflow_events.values())
        return ordered[-limit:]


def _reject_collision(
    existing: Iterable[tuple[BsonObjectId, tuple[object, ...]]],
    *,
    new_id: BsonObjectId,
    new_key: tuple[object, ...],
    label: str,
) -> None:
    for record_id, key in existing:
        if record_id != new_id and key == new_key:
            raise DuplicateRecordError(f"Duplicate {label}: {new_key}")


def _target_repo_key(repo: TargetRepo) -> tuple[str, str, str]:
    return (repo.provider.value, repo.owner, repo.name)


def _source_observation_key(observation: SourceObservation) -> tuple[object, ...]:
    return (
        observation.source_connection_id,
        observation.external_id,
        observation.content_hash.value,
    )


def _sync_cursor_key(cursor: SyncCursor) -> tuple[object, ...]:
    return (cursor.source_connection_id, cursor.cursor_name)


def _tracker_issue_key(work_item: WorkItem) -> tuple[str, str]:
    if work_item.tracker_issue is None:
        return ("", "")
    return (
        work_item.tracker_issue.provider,
        str(work_item.tracker_issue.issue_number),
    )


def _tool_policy_key(policy: ToolPolicy) -> tuple[object, ...]:
    return (policy.project.id, policy.tool_type, policy.action_type)


def _matches_observation_query(
    observation: SourceObservation, query: SourceObservationQuery
) -> bool:
    return (
        observation.source_connection_id == query.source_connection_id
        and (not query.external_id or observation.external_id == query.external_id)
        and (
            not query.content_hash_value
            or observation.content_hash.value == query.content_hash_value
        )
    )


def _matches_waiting_gate(gate: ApprovalGate, query: WaitingGateQuery, store: _MemoryStore) -> bool:
    if query.work_item_id and gate.work_item_id != query.work_item_id:
        return False
    if query.tracker_issue_number is None:
        return True
    work_item = store.work_items.get(gate.work_item_id)
    return (
        work_item is not None
        and work_item.tracker_issue is not None
        and work_item.tracker_issue.issue_number == query.tracker_issue_number
    )


def _matches_tool_action(
    project_id: BsonObjectId | None,
    tool_type: str,
    action_type: str,
    query: ToolActionQuery,
) -> bool:
    return (
        (not query.project_id or project_id == query.project_id)
        and (not query.tool_type or tool_type == query.tool_type)
        and (not query.action_type or action_type == query.action_type)
    )


def _invocation_project_id(invocation: ToolInvocation, store: _MemoryStore) -> BsonObjectId | None:
    if invocation.action_request_id is None:
        return None
    request = store.action_requests.get(invocation.action_request_id)
    if request is None:
        return None
    return request.project.id


def _is_runnable(
    work_item: WorkItem,
    state_record: WorkflowStateRecord | None,
    query: RunnableWorkQuery,
) -> bool:
    stage = state_record.state.stage if state_record is not None else work_item.workflow_stage
    status = state_record.state.status if state_record is not None else work_item.status
    risk = state_record.state.risk if state_record is not None else work_item.risk
    blockers = state_record.state.blockers if state_record is not None else ()
    lease = state_record.state.lease if state_record is not None else None

    return (
        stage == query.workflow_stage
        and status == query.status
        and (query.risk is None or risk == query.risk)
        and (not query.project_id or work_item.target_repo.project.id == query.project_id)
        and (not query.target_repo_id or work_item.target_repo.id == query.target_repo_id)
        and (
            query.include_blocked
            or (not work_item.blocker_summaries and not _has_active_blockers(blockers))
        )
        and (query.now is None or lease is None or lease.expires_at <= query.now)
    )


def _has_active_blockers(blockers: Sequence[Blocker]) -> bool:
    return any(blocker.resolved_at is None for blocker in blockers)


def _sorted_by_id[T](items: Iterable[T], key: Callable[[T], object]) -> tuple[T, ...]:
    return tuple(sorted(items, key=lambda item: str(key(item))))


def _sorted_work_items(items: Iterable[WorkItem]) -> tuple[WorkItem, ...]:
    return tuple(sorted(items, key=lambda item: (item.created_at, str(item.id))))


def _sorted_state_records(items: Iterable[WorkflowStateRecord]) -> tuple[WorkflowStateRecord, ...]:
    return tuple(sorted(items, key=lambda item: (item.updated_at, str(item.id))))


def _sorted_gates(items: Iterable[ApprovalGate]) -> tuple[ApprovalGate, ...]:
    return tuple(sorted(items, key=lambda item: (item.created_at, str(item.id))))


def _sorted_invocations(items: Iterable[ToolInvocation]) -> tuple[ToolInvocation, ...]:
    return tuple(sorted(items, key=lambda item: (item.happened_at, str(item.id))))


def _sorted_events(items: Iterable[WorkflowEvent]) -> tuple[WorkflowEvent, ...]:
    return tuple(sorted(items, key=lambda item: (item.happened_at, str(item.id))))
