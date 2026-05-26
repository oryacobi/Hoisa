"""Deterministic in-memory persistence adapter for Hoisa tests."""

from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field
from typing import Any

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
    CatalogGateway,
    DuplicateRecordError,
    EventGateway,
    EvidenceGateway,
    LeaseLookupQuery,
    PersistenceProvider,
    RepoLookup,
    RunnableWorkQuery,
    SourceGateway,
    SourceObservationQuery,
    SyncCursorKey,
    ToolActionQuery,
    ToolGateway,
    WaitingGateQuery,
    WorkflowGateway,
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


@dataclass(slots=True)
class _MemoryEntityStore[T]:
    records: dict[BsonObjectId, T]
    duplicate_label: str
    key: Callable[[T], BsonObjectId]
    unique_keys: tuple[Callable[[T], tuple[object, ...] | None], ...] = ()

    def save(self, entity: T) -> None:
        entity_id = self.key(entity)
        self._reject_unique_collisions(entity, entity_id)
        self.records[entity_id] = entity

    def insert(self, entity: T) -> None:
        entity_id = self.key(entity)
        if entity_id in self.records:
            raise DuplicateRecordError(f"{self.duplicate_label} already exists: {entity_id}")
        self._reject_unique_collisions(entity, entity_id)
        self.records[entity_id] = entity

    def get(self, entity_id: BsonObjectId) -> T | None:
        return self.records.get(entity_id)

    def find(
        self,
        predicate: Callable[[T], bool] | None = None,
        *,
        sort_key: Callable[[T], Any] | None = None,
    ) -> tuple[T, ...]:
        selected = (
            entity for entity in self.records.values() if predicate is None or predicate(entity)
        )
        key = sort_key or (lambda entity: str(self.key(entity)))
        return tuple(sorted(selected, key=key))

    def _reject_unique_collisions(self, entity: T, entity_id: BsonObjectId) -> None:
        for unique_key in self.unique_keys:
            new_key = unique_key(entity)
            if new_key is None:
                continue
            for existing in self.records.values():
                existing_key = unique_key(existing)
                if self.key(existing) != entity_id and existing_key == new_key:
                    raise DuplicateRecordError(f"Duplicate {self.duplicate_label}: {new_key}")


class InMemoryPersistenceProvider(PersistenceProvider):
    """In-memory implementation of Hoisa persistence gateways."""

    def __init__(self) -> None:
        store = _MemoryStore()
        self._catalog = _InMemoryCatalogGateway(store)
        self._sources = _InMemorySourceGateway(store)
        self._workflow = _InMemoryWorkflowGateway(store)
        self._evidence = _InMemoryEvidenceGateway(store)
        self._tools = _InMemoryToolGateway(store)
        self._events = _InMemoryEventGateway(store)

    @property
    def catalog(self) -> CatalogGateway:
        """Return the project and target-repo gateway."""

        return self._catalog

    @property
    def sources(self) -> SourceGateway:
        """Return the source data gateway."""

        return self._sources

    @property
    def workflow(self) -> WorkflowGateway:
        """Return the workflow state gateway."""

        return self._workflow

    @property
    def evidence(self) -> EvidenceGateway:
        """Return the evidence gateway."""

        return self._evidence

    @property
    def tools(self) -> ToolGateway:
        """Return the tool-control gateway."""

        return self._tools

    @property
    def events(self) -> EventGateway:
        """Return the workflow event gateway."""

        return self._events


class _InMemoryCatalogGateway:
    def __init__(self, store: _MemoryStore) -> None:
        self._projects = _MemoryEntityStore(store.projects, "project", lambda project: project.id)
        self._target_repos = _MemoryEntityStore(
            store.target_repos,
            "target repository",
            lambda repo: repo.id,
            unique_keys=(_target_repo_key,),
        )

    async def save_project(self, project: Project) -> None:
        self._projects.save(project)

    async def get_project(self, project_id: BsonObjectId) -> Project | None:
        return self._projects.get(project_id)

    async def list_projects(self) -> Sequence[Project]:
        return self._projects.find()

    async def save_target_repo(self, target_repo: TargetRepo) -> None:
        self._target_repos.save(target_repo)

    async def get_target_repo(self, target_repo_id: BsonObjectId) -> TargetRepo | None:
        return self._target_repos.get(target_repo_id)

    async def get_target_repo_by_provider(self, lookup: RepoLookup) -> TargetRepo | None:
        key = (lookup.provider.value, lookup.owner, lookup.name)
        for repo in self._target_repos.records.values():
            if _target_repo_key(repo) == key:
                return repo
        return None

    async def list_target_repos(self, project_id: BsonObjectId) -> Sequence[TargetRepo]:
        return self._target_repos.find(lambda repo: repo.project.id == project_id)


class _InMemorySourceGateway:
    def __init__(self, store: _MemoryStore) -> None:
        self._connections = _MemoryEntityStore(
            store.source_connections,
            "source connection",
            lambda connection: connection.id,
        )
        self._observations = _MemoryEntityStore(
            store.source_observations,
            "source observation",
            lambda observation: observation.id,
            unique_keys=(_source_observation_key,),
        )
        self._cursors = _MemoryEntityStore(
            store.sync_cursors,
            "sync cursor",
            lambda cursor: cursor.id,
            unique_keys=(_sync_cursor_unique_key,),
        )

    async def save_connection(self, connection: SourceConnection) -> None:
        self._connections.save(connection)

    async def get_connection(self, source_connection_id: BsonObjectId) -> SourceConnection | None:
        return self._connections.get(source_connection_id)

    async def list_connections(self, project_id: BsonObjectId) -> Sequence[SourceConnection]:
        return self._connections.find(
            lambda connection: connection.project.id == project_id,
        )

    async def save_observation(self, observation: SourceObservation) -> None:
        self._observations.save(observation)

    async def get_observation(self, observation_id: BsonObjectId) -> SourceObservation | None:
        return self._observations.get(observation_id)

    async def find_observations(self, query: SourceObservationQuery) -> Sequence[SourceObservation]:
        return self._observations.find(
            lambda observation: _matches_observation_query(observation, query)
        )

    async def save_cursor(self, cursor: SyncCursor) -> None:
        self._cursors.save(cursor)

    async def get_cursor(self, key: SyncCursorKey) -> SyncCursor | None:
        target = (key.source_connection_id, key.cursor_name)
        for cursor in self._cursors.records.values():
            if _sync_cursor_unique_key(cursor) == target:
                return cursor
        return None

    async def list_cursors(self, source_connection_id: BsonObjectId) -> Sequence[SyncCursor]:
        return self._cursors.find(
            lambda cursor: cursor.source_connection_id == source_connection_id,
        )


class _InMemoryWorkflowGateway:
    def __init__(self, store: _MemoryStore) -> None:
        self._store = store
        self._work_items = _MemoryEntityStore(
            store.work_items,
            "work item tracker issue",
            lambda work_item: work_item.id,
            unique_keys=(_tracker_issue_key,),
        )
        self._states = _MemoryEntityStore(
            store.workflow_states,
            "workflow state",
            lambda state: state.id,
        )
        self._gates = _MemoryEntityStore(store.gates, "approval gate", lambda gate: gate.id)
        self._agent_runs = _MemoryEntityStore(
            store.agent_runs,
            "agent run",
            lambda run: run.id,
        )

    async def save_work_item(self, work_item: WorkItem) -> None:
        self._work_items.save(work_item)

    async def get_work_item(self, work_item_id: BsonObjectId) -> WorkItem | None:
        return self._work_items.get(work_item_id)

    async def find_work_item_by_tracker_issue(
        self, *, provider: str, issue_number: int
    ) -> WorkItem | None:
        for work_item in self._work_items.records.values():
            if (
                work_item.tracker_issue is not None
                and work_item.tracker_issue.provider == provider
                and work_item.tracker_issue.issue_number == issue_number
            ):
                return work_item
        return None

    async def find_runnable_work(self, query: RunnableWorkQuery) -> Sequence[WorkItem]:
        return _sorted_work_items(
            work_item
            for work_item in self._work_items.records.values()
            if _is_runnable(work_item, self._store.workflow_states.get(work_item.id), query)
        )

    async def save_state(self, state_record: WorkflowStateRecord) -> None:
        self._states.save(state_record)

    async def get_state(self, work_item_id: BsonObjectId) -> WorkflowStateRecord | None:
        return self._states.get(work_item_id)

    async def list_states_by_worker(self, query: LeaseLookupQuery) -> Sequence[WorkflowStateRecord]:
        return _sorted_state_records(
            record
            for record in self._states.records.values()
            if record.state.lease is not None
            and (not query.worker_id or record.state.lease.worker_id == query.worker_id)
        )

    async def list_active_leases(self, query: LeaseLookupQuery) -> Sequence[WorkflowStateRecord]:
        return _sorted_state_records(
            record
            for record in self._states.records.values()
            if record.state.lease is not None
            and (not query.worker_id or record.state.lease.worker_id == query.worker_id)
            and (query.now is None or record.state.lease.expires_at > query.now)
        )

    async def list_expired_leases(self, query: LeaseLookupQuery) -> Sequence[WorkflowStateRecord]:
        if query.now is None:
            return ()
        return _sorted_state_records(
            record
            for record in self._states.records.values()
            if record.state.lease is not None
            and (not query.worker_id or record.state.lease.worker_id == query.worker_id)
            and record.state.lease.expires_at <= query.now
        )

    async def save_gate(self, gate: ApprovalGate) -> None:
        self._gates.save(gate)

    async def get_gate(self, gate_id: BsonObjectId) -> ApprovalGate | None:
        return self._gates.get(gate_id)

    async def list_gates(self, work_item_id: BsonObjectId) -> Sequence[ApprovalGate]:
        return _sorted_gates(
            gate for gate in self._gates.records.values() if gate.work_item_id == work_item_id
        )

    async def list_waiting_gates(self, query: WaitingGateQuery) -> Sequence[ApprovalGate]:
        return _sorted_gates(
            gate
            for gate in self._gates.records.values()
            if gate.gate_status == GateStatus.WAITING
            and _matches_waiting_gate(gate, query, self._store)
        )

    async def save_agent_run(self, run: AgentRun) -> None:
        self._agent_runs.save(run)

    async def get_agent_run(self, run_id: BsonObjectId) -> AgentRun | None:
        return self._agent_runs.get(run_id)

    async def list_agent_runs(self, work_item_id: BsonObjectId) -> Sequence[AgentRun]:
        return self._agent_runs.find(lambda run: run.work_item_id == work_item_id)


class _InMemoryEvidenceGateway:
    def __init__(self, store: _MemoryStore) -> None:
        self._bundles = _MemoryEntityStore(
            store.evidence_bundles,
            "evidence bundle",
            lambda bundle: bundle.id,
        )

    async def save_bundle(self, bundle: EvidenceBundle) -> None:
        self._bundles.save(bundle)

    async def get_bundle(self, bundle_id: BsonObjectId) -> EvidenceBundle | None:
        return self._bundles.get(bundle_id)

    async def list_bundles(
        self, *, subject_type: str, subject_id: BsonObjectId
    ) -> Sequence[EvidenceBundle]:
        return self._bundles.find(
            lambda bundle: bundle.subject_type == subject_type and bundle.subject_id == subject_id,
        )


class _InMemoryToolGateway:
    def __init__(self, store: _MemoryStore) -> None:
        self._store = store
        self._connections = _MemoryEntityStore(
            store.tool_connections,
            "tool connection",
            lambda connection: connection.id,
        )
        self._policies = _MemoryEntityStore(
            store.tool_policies,
            "tool policy",
            lambda policy: policy.id,
            unique_keys=(_tool_policy_key,),
        )
        self._action_requests = _MemoryEntityStore(
            store.action_requests,
            "action request",
            lambda request: request.id,
        )
        self._invocations = _MemoryEntityStore(
            store.tool_invocations,
            "tool invocation",
            lambda invocation: invocation.id,
        )

    async def save_connection(self, connection: ToolConnection) -> None:
        self._connections.save(connection)

    async def get_connection(self, tool_connection_id: BsonObjectId) -> ToolConnection | None:
        return self._connections.get(tool_connection_id)

    async def list_connections(self, project_id: BsonObjectId) -> Sequence[ToolConnection]:
        return self._connections.find(
            lambda connection: connection.project.id == project_id,
        )

    async def save_policy(self, policy: ToolPolicy) -> None:
        self._policies.save(policy)

    async def get_policy(self, tool_policy_id: BsonObjectId) -> ToolPolicy | None:
        return self._policies.get(tool_policy_id)

    async def find_policies(self, query: ToolActionQuery) -> Sequence[ToolPolicy]:
        return self._policies.find(
            lambda policy: _matches_tool_action(
                policy.project.id,
                policy.tool_type,
                policy.action_type,
                query,
            )
        )

    async def save_action_request(self, request: ActionRequest) -> None:
        self._action_requests.save(request)

    async def get_action_request(self, action_request_id: BsonObjectId) -> ActionRequest | None:
        return self._action_requests.get(action_request_id)

    async def list_action_requests_by_status(
        self, status: ActionRequestStatus
    ) -> Sequence[ActionRequest]:
        return self._action_requests.find(lambda request: request.status == status)

    async def list_action_requests_for_gate(self, gate_id: BsonObjectId) -> Sequence[ActionRequest]:
        return self._action_requests.find(lambda request: request.required_gate_id == gate_id)

    async def save_invocation(self, invocation: ToolInvocation) -> None:
        self._invocations.save(invocation)

    async def get_invocation(self, tool_invocation_id: BsonObjectId) -> ToolInvocation | None:
        return self._invocations.get(tool_invocation_id)

    async def list_invocations_for_action_request(
        self, action_request_id: BsonObjectId
    ) -> Sequence[ToolInvocation]:
        return _sorted_invocations(
            invocation
            for invocation in self._invocations.records.values()
            if invocation.action_request_id == action_request_id
        )

    async def list_invocations_by_tool_action(
        self,
        query: ToolActionQuery,
        *,
        status: ToolInvocationStatus | None = None,
    ) -> Sequence[ToolInvocation]:
        project_request_ids: set[BsonObjectId] | None = None
        if query.project_id is not None:
            project_request_ids = {
                request.id
                for request in self._action_requests.records.values()
                if request.project.id == query.project_id
            }
        return _sorted_invocations(
            invocation
            for invocation in self._invocations.records.values()
            if _matches_tool_surface(invocation.tool_type, invocation.action_type, query)
            and (status is None or invocation.status == status)
            and (project_request_ids is None or invocation.action_request_id in project_request_ids)
        )


class _InMemoryEventGateway:
    def __init__(self, store: _MemoryStore) -> None:
        self._events = _MemoryEntityStore(
            store.workflow_events,
            "Workflow event",
            lambda event: event.id,
        )

    async def append(self, event: WorkflowEvent) -> None:
        self._events.insert(event)

    async def get(self, event_id: BsonObjectId) -> WorkflowEvent | None:
        return self._events.get(event_id)

    async def list_for_subject(self, subject: EventSubject) -> Sequence[WorkflowEvent]:
        return _sorted_events(
            event for event in self._events.records.values() if event.subject == subject
        )

    async def list_for_correlation(self, correlation_id: str) -> Sequence[WorkflowEvent]:
        return _sorted_events(
            event
            for event in self._events.records.values()
            if event.correlation_id == correlation_id
        )

    async def list_recent(self, *, limit: int) -> Sequence[WorkflowEvent]:
        if limit <= 0:
            return ()
        ordered = _sorted_events(self._events.records.values())
        return ordered[-limit:]


def _target_repo_key(repo: TargetRepo) -> tuple[object, ...]:
    return (repo.provider.value, repo.owner, repo.name)


def _source_observation_key(observation: SourceObservation) -> tuple[object, ...]:
    return (
        observation.source_connection_id,
        observation.external_id,
        observation.content_hash.value,
    )


def _sync_cursor_unique_key(cursor: SyncCursor) -> tuple[object, ...]:
    return (cursor.source_connection_id, cursor.cursor_name)


def _tracker_issue_key(work_item: WorkItem) -> tuple[object, ...] | None:
    if work_item.tracker_issue is None:
        return None
    return (
        work_item.tracker_issue.provider,
        work_item.tracker_issue.issue_number,
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
        (query.project_id is None or project_id == query.project_id)
        and (not query.tool_type or tool_type == query.tool_type)
        and (not query.action_type or action_type == query.action_type)
    )


def _matches_tool_surface(tool_type: str, action_type: str, query: ToolActionQuery) -> bool:
    return (not query.tool_type or tool_type == query.tool_type) and (
        not query.action_type or action_type == query.action_type
    )


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
        and (query.project_id is None or work_item.target_repo.project.id == query.project_id)
        and (query.target_repo_id is None or work_item.target_repo.id == query.target_repo_id)
        and (
            query.include_blocked
            or (not work_item.blocker_summaries and not _has_active_blockers(blockers))
        )
        and (query.now is None or lease is None or lease.expires_at <= query.now)
    )


def _has_active_blockers(blockers: Sequence[Blocker]) -> bool:
    return any(blocker.resolved_at is None for blocker in blockers)


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
