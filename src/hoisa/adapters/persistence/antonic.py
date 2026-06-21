"""Antonic-backed persistence adapter for Hoisa's local MongoDB runtime."""

from collections.abc import Mapping, Sequence
from typing import Any

from antonic import AntConnector, DuplicateAntDocError, OptimisticLockError

from hoisa.domain.directives import Directive
from hoisa.domain.events import EventSubject, WorkflowEvent
from hoisa.domain.evidence import EvidenceBundle
from hoisa.domain.gates import ApprovalGate, GateStatus
from hoisa.domain.models import ASCENDING, CollectionRoot
from hoisa.domain.runs import AgentRun
from hoisa.domain.sources import SourceConnection, SourceObservation, SyncCursor
from hoisa.domain.target_repos import Project, TargetRepo
from hoisa.domain.task_packets import TaskPacket
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
    PersistenceConflictError,
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

DURABLE_RECORD_TYPES: tuple[type[CollectionRoot], ...] = (
    Project,
    TargetRepo,
    SourceConnection,
    SourceObservation,
    SyncCursor,
    WorkItem,
    WorkflowStateRecord,
    ApprovalGate,
    AgentRun,
    EvidenceBundle,
    ToolConnection,
    ToolPolicy,
    ActionRequest,
    ToolInvocation,
    WorkflowEvent,
    Directive,
    TaskPacket,
)

_SORT_BY_ID = [("id", ASCENDING)]
_SORT_BY_CREATED_ID = [("created_at", ASCENDING), ("id", ASCENDING)]
_SORT_BY_UPDATED_ID = [("updated_at", ASCENDING), ("id", ASCENDING)]


class AntonicPersistenceProvider(PersistenceProvider):
    """Persistence provider backed by Antonic and the configured MongoDB URI."""

    def __init__(self, connector: AntConnector | None = None) -> None:
        self._connector = connector or AntConnector()
        self._connector.register(*DURABLE_RECORD_TYPES)
        self._projects = _AntonicProjectRepository(self._connector)
        self._target_repos = _AntonicTargetRepoRepository(self._connector)
        self._source_connections = _AntonicSourceConnectionRepository(self._connector)
        self._source_observations = _AntonicSourceObservationRepository(self._connector)
        self._sync_cursors = _AntonicSyncCursorRepository(self._connector)
        self._work_items = _AntonicWorkItemRepository(self._connector)
        self._workflow_states = _AntonicWorkflowStateRepository(self._connector)
        self._gates = _AntonicApprovalGateRepository(self._connector)
        self._agent_runs = _AntonicAgentRunRepository(self._connector)
        self._evidence_bundles = _AntonicEvidenceBundleRepository(self._connector)
        self._tool_connections = _AntonicToolConnectionRepository(self._connector)
        self._tool_policies = _AntonicToolPolicyRepository(self._connector)
        self._action_requests = _AntonicActionRequestRepository(self._connector)
        self._tool_invocations = _AntonicToolInvocationRepository(self._connector)
        self._workflow_events = _AntonicWorkflowEventStore(self._connector)

    async def close(self) -> None:
        """Close the underlying Antonic connector."""

        await self._connector.close()

    async def ensure_indexes(self) -> None:
        """Ensure indexes declared on Hoisa durable record types."""

        await self._connector.ensure_indexes(*DURABLE_RECORD_TYPES)

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


class _AntonicProjectRepository:
    def __init__(self, connector: AntConnector) -> None:
        self._connector = connector

    async def save(self, project: Project) -> None:
        await _save(self._connector, project)

    async def get(self, project_id: str) -> Project | None:
        return await self._connector.get(Project, project_id)

    async def list_all(self) -> Sequence[Project]:
        return tuple(await self._connector.find(Project, sort=_SORT_BY_ID))


class _AntonicTargetRepoRepository:
    def __init__(self, connector: AntConnector) -> None:
        self._connector = connector

    async def save(self, target_repo: TargetRepo) -> None:
        await _save(self._connector, target_repo)

    async def get(self, target_repo_id: str) -> TargetRepo | None:
        return await self._connector.get(TargetRepo, target_repo_id)

    async def get_by_provider(self, lookup: RepoLookup) -> TargetRepo | None:
        return await self._connector.get(
            TargetRepo,
            filter={
                "provider": lookup.provider,
                "owner": lookup.owner,
                "name": lookup.name,
            },
        )

    async def list_by_project(self, project_id: str) -> Sequence[TargetRepo]:
        return tuple(
            await self._connector.find(
                TargetRepo,
                filter={"project.project_id": project_id},
                sort=_SORT_BY_ID,
            )
        )


class _AntonicSourceConnectionRepository:
    def __init__(self, connector: AntConnector) -> None:
        self._connector = connector

    async def save(self, connection: SourceConnection) -> None:
        await _save(self._connector, connection)

    async def get(self, source_connection_id: str) -> SourceConnection | None:
        return await self._connector.get(SourceConnection, source_connection_id)

    async def list_by_project(self, project_id: str) -> Sequence[SourceConnection]:
        return tuple(
            await self._connector.find(
                SourceConnection,
                filter={"project.project_id": project_id},
                sort=_SORT_BY_ID,
            )
        )


class _AntonicSourceObservationRepository:
    def __init__(self, connector: AntConnector) -> None:
        self._connector = connector

    async def save(self, observation: SourceObservation) -> None:
        await _save(self._connector, observation)

    async def get(self, observation_id: str) -> SourceObservation | None:
        return await self._connector.get(SourceObservation, observation_id)

    async def find_by_source(self, query: SourceObservationQuery) -> Sequence[SourceObservation]:
        filters: dict[str, Any] = {"source_connection_id": query.source_connection_id}
        if query.external_id:
            filters["external_id"] = query.external_id
        if query.content_hash_value:
            filters["content_hash.value"] = query.content_hash_value
        return tuple(
            await self._connector.find(
                SourceObservation,
                filter=filters,
                sort=_SORT_BY_ID,
            )
        )


class _AntonicSyncCursorRepository:
    def __init__(self, connector: AntConnector) -> None:
        self._connector = connector

    async def save(self, cursor: SyncCursor) -> None:
        await _save(self._connector, cursor)

    async def get(self, key: SyncCursorKey) -> SyncCursor | None:
        return await self._connector.get(
            SyncCursor,
            filter={
                "source_connection_id": key.source_connection_id,
                "cursor_name": key.cursor_name,
            },
        )

    async def list_by_source(self, source_connection_id: str) -> Sequence[SyncCursor]:
        return tuple(
            await self._connector.find(
                SyncCursor,
                filter={"source_connection_id": source_connection_id},
                sort=_SORT_BY_ID,
            )
        )


class _AntonicWorkItemRepository:
    def __init__(self, connector: AntConnector) -> None:
        self._connector = connector

    async def save(self, work_item: WorkItem) -> None:
        await _save(self._connector, work_item)

    async def get(self, work_item_id: str) -> WorkItem | None:
        return await self._connector.get(WorkItem, work_item_id)

    async def find_by_tracker_issue(self, *, provider: str, issue_number: int) -> WorkItem | None:
        return await self._connector.get(
            WorkItem,
            filter={
                "tracker_issue.provider": provider,
                "tracker_issue.issue_number": issue_number,
            },
        )

    async def find_runnable(self, query: RunnableWorkQuery) -> Sequence[WorkItem]:
        items = await self._connector.find(WorkItem, sort=_SORT_BY_CREATED_ID)
        runnable: list[WorkItem] = []
        for item in items:
            state = await self._connector.get(WorkflowStateRecord, item.id)
            if _is_runnable(item, state, query):
                runnable.append(item)
        return tuple(runnable)


class _AntonicWorkflowStateRepository:
    def __init__(self, connector: AntConnector) -> None:
        self._connector = connector

    async def save(self, state_record: WorkflowStateRecord) -> None:
        await _save(self._connector, state_record)

    async def get(self, work_item_id: str) -> WorkflowStateRecord | None:
        return await self._connector.get(WorkflowStateRecord, work_item_id)

    async def list_by_worker(self, query: LeaseLookupQuery) -> Sequence[WorkflowStateRecord]:
        filters = _worker_filter(query)
        return tuple(
            await self._connector.find(
                WorkflowStateRecord, filter=filters, sort=_SORT_BY_UPDATED_ID
            )
        )

    async def list_active_leases(self, query: LeaseLookupQuery) -> Sequence[WorkflowStateRecord]:
        records = await self._connector.find(
            WorkflowStateRecord,
            filter=_worker_filter(query),
            sort=_SORT_BY_UPDATED_ID,
        )
        return tuple(
            record
            for record in records
            if record.state.lease is not None
            and (query.now is None or record.state.lease.expires_at > query.now)
        )

    async def list_expired_leases(self, query: LeaseLookupQuery) -> Sequence[WorkflowStateRecord]:
        if query.now is None:
            return ()
        records = await self._connector.find(
            WorkflowStateRecord,
            filter=_worker_filter(query),
            sort=_SORT_BY_UPDATED_ID,
        )
        return tuple(
            record
            for record in records
            if record.state.lease is not None and record.state.lease.expires_at <= query.now
        )


class _AntonicApprovalGateRepository:
    def __init__(self, connector: AntConnector) -> None:
        self._connector = connector

    async def save(self, gate: ApprovalGate) -> None:
        await _save(self._connector, gate)

    async def get(self, gate_id: str) -> ApprovalGate | None:
        return await self._connector.get(ApprovalGate, gate_id)

    async def list_by_work_item(self, work_item_id: str) -> Sequence[ApprovalGate]:
        return tuple(
            await self._connector.find(
                ApprovalGate,
                filter={"work_item_id": work_item_id},
                sort=_SORT_BY_CREATED_ID,
            )
        )

    async def list_waiting(self, query: WaitingGateQuery) -> Sequence[ApprovalGate]:
        filters: dict[str, Any] = {"gate_status": GateStatus.WAITING}
        if query.work_item_id:
            filters["work_item_id"] = query.work_item_id
        gates = await self._connector.find(ApprovalGate, filter=filters, sort=_SORT_BY_CREATED_ID)
        if query.tracker_issue_number is None:
            return tuple(gates)

        waiting: list[ApprovalGate] = []
        for gate in gates:
            work_item = await self._connector.get(WorkItem, gate.work_item_id)
            if (
                work_item is not None
                and work_item.tracker_issue is not None
                and work_item.tracker_issue.issue_number == query.tracker_issue_number
            ):
                waiting.append(gate)
        return tuple(waiting)


class _AntonicAgentRunRepository:
    def __init__(self, connector: AntConnector) -> None:
        self._connector = connector

    async def save(self, run: AgentRun) -> None:
        await _save(self._connector, run)

    async def get(self, run_id: str) -> AgentRun | None:
        return await self._connector.get(AgentRun, run_id)

    async def list_by_work_item(self, work_item_id: str) -> Sequence[AgentRun]:
        return tuple(
            await self._connector.find(
                AgentRun,
                filter={"work_item_id": work_item_id},
                sort=_SORT_BY_ID,
            )
        )


class _AntonicEvidenceBundleRepository:
    def __init__(self, connector: AntConnector) -> None:
        self._connector = connector

    async def save(self, bundle: EvidenceBundle) -> None:
        await _save(self._connector, bundle)

    async def get(self, bundle_id: str) -> EvidenceBundle | None:
        return await self._connector.get(EvidenceBundle, bundle_id)

    async def list_by_subject(
        self, *, subject_type: str, subject_id: str
    ) -> Sequence[EvidenceBundle]:
        return tuple(
            await self._connector.find(
                EvidenceBundle,
                filter={"subject_type": subject_type, "subject_id": subject_id},
                sort=_SORT_BY_ID,
            )
        )


class _AntonicToolConnectionRepository:
    def __init__(self, connector: AntConnector) -> None:
        self._connector = connector

    async def save(self, connection: ToolConnection) -> None:
        await _save(self._connector, connection)

    async def get(self, tool_connection_id: str) -> ToolConnection | None:
        return await self._connector.get(ToolConnection, tool_connection_id)

    async def list_by_project(self, project_id: str) -> Sequence[ToolConnection]:
        return tuple(
            await self._connector.find(
                ToolConnection,
                filter={"project.project_id": project_id},
                sort=_SORT_BY_ID,
            )
        )


class _AntonicToolPolicyRepository:
    def __init__(self, connector: AntConnector) -> None:
        self._connector = connector

    async def save(self, policy: ToolPolicy) -> None:
        await _save(self._connector, policy)

    async def get(self, tool_policy_id: str) -> ToolPolicy | None:
        return await self._connector.get(ToolPolicy, tool_policy_id)

    async def find_for_action(self, query: ToolActionQuery) -> Sequence[ToolPolicy]:
        return tuple(
            await self._connector.find(
                ToolPolicy,
                filter=_tool_action_filter(query),
                sort=_SORT_BY_ID,
            )
        )


class _AntonicActionRequestRepository:
    def __init__(self, connector: AntConnector) -> None:
        self._connector = connector

    async def save(self, request: ActionRequest) -> None:
        await _save(self._connector, request)

    async def get(self, action_request_id: str) -> ActionRequest | None:
        return await self._connector.get(ActionRequest, action_request_id)

    async def list_by_status(self, status: ActionRequestStatus) -> Sequence[ActionRequest]:
        return tuple(
            await self._connector.find(
                ActionRequest,
                filter={"status": status},
                sort=_SORT_BY_ID,
            )
        )

    async def list_for_gate(self, gate_id: str) -> Sequence[ActionRequest]:
        return tuple(
            await self._connector.find(
                ActionRequest,
                filter={"required_gate_id": gate_id},
                sort=_SORT_BY_ID,
            )
        )


class _AntonicToolInvocationRepository:
    def __init__(self, connector: AntConnector) -> None:
        self._connector = connector

    async def save(self, invocation: ToolInvocation) -> None:
        await _save(self._connector, invocation)

    async def get(self, tool_invocation_id: str) -> ToolInvocation | None:
        return await self._connector.get(ToolInvocation, tool_invocation_id)

    async def list_for_action_request(self, action_request_id: str) -> Sequence[ToolInvocation]:
        return tuple(
            await self._connector.find(
                ToolInvocation,
                filter={"action_request_id": action_request_id},
                sort=[("happened_at", ASCENDING), ("id", ASCENDING)],
            )
        )

    async def list_by_tool_action(
        self,
        query: ToolActionQuery,
        *,
        status: ToolInvocationStatus | None = None,
    ) -> Sequence[ToolInvocation]:
        filters: dict[str, Any] = {
            key: value
            for key, value in {
                "tool_type": query.tool_type,
                "action_type": query.action_type,
                "status": status,
            }.items()
            if value
        }
        invocations = await self._connector.find(
            ToolInvocation,
            filter=filters,
            sort=[("happened_at", ASCENDING), ("id", ASCENDING)],
        )
        if not query.project_id:
            return tuple(invocations)

        matched: list[ToolInvocation] = []
        for invocation in invocations:
            if await _invocation_project_id(self._connector, invocation) == query.project_id:
                matched.append(invocation)
        return tuple(matched)


class _AntonicWorkflowEventStore:
    def __init__(self, connector: AntConnector) -> None:
        self._connector = connector

    async def append(self, event: WorkflowEvent) -> None:
        if await self._connector.get(WorkflowEvent, event.id) is not None:
            raise DuplicateRecordError(f"Workflow event already exists: {event.id}")
        await _insert(self._connector, event)

    async def get(self, event_id: str) -> WorkflowEvent | None:
        return await self._connector.get(WorkflowEvent, event_id)

    async def list_for_subject(self, subject: EventSubject) -> Sequence[WorkflowEvent]:
        return tuple(
            await self._connector.find(
                WorkflowEvent,
                filter={
                    "subject.subject_type": subject.subject_type,
                    "subject.subject_id": subject.subject_id,
                },
                sort=[("happened_at", ASCENDING), ("id", ASCENDING)],
            )
        )

    async def list_for_correlation(self, correlation_id: str) -> Sequence[WorkflowEvent]:
        return tuple(
            await self._connector.find(
                WorkflowEvent,
                filter={"correlation_id": correlation_id},
                sort=[("happened_at", ASCENDING), ("id", ASCENDING)],
            )
        )

    async def list_recent(self, *, limit: int) -> Sequence[WorkflowEvent]:
        if limit <= 0:
            return ()
        events = await self._connector.find(
            WorkflowEvent,
            sort=[("happened_at", ASCENDING), ("id", ASCENDING)],
        )
        return tuple(events[-limit:])


async def _save[TRecord: CollectionRoot](connector: AntConnector, record: TRecord) -> None:
    existing = await connector.get(type(record), record.id)
    if existing is not None and record.version == 0:
        record = record.model_copy(update={"version": existing.version})
    try:
        if existing is None:
            await connector.insert(record)
        else:
            await connector.save(record)
    except DuplicateAntDocError as exc:
        raise DuplicateRecordError(str(exc)) from exc
    except OptimisticLockError as exc:
        raise PersistenceConflictError(str(exc)) from exc


async def _insert[TRecord: CollectionRoot](connector: AntConnector, record: TRecord) -> None:
    try:
        await connector.insert(record)
    except DuplicateAntDocError as exc:
        raise DuplicateRecordError(str(exc)) from exc


def _worker_filter(query: LeaseLookupQuery) -> Mapping[str, Any]:
    if not query.worker_id:
        return {}
    return {"state.lease.worker_id": query.worker_id}


def _tool_action_filter(query: ToolActionQuery) -> dict[str, Any]:
    return {
        key: value
        for key, value in {
            "project.project_id": query.project_id,
            "tool_type": query.tool_type,
            "action_type": query.action_type,
        }.items()
        if value
    }


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
        and (not query.project_id or work_item.target_repo.project.project_id == query.project_id)
        and (
            not query.target_repo_id or work_item.target_repo.target_repo_id == query.target_repo_id
        )
        and (
            query.include_blocked
            or (not work_item.blocker_summaries and not _has_active_blockers(blockers))
        )
        and (query.now is None or lease is None or lease.expires_at <= query.now)
    )


def _has_active_blockers(blockers: Sequence[Blocker]) -> bool:
    return any(blocker.resolved_at is None for blocker in blockers)


async def _invocation_project_id(connector: AntConnector, invocation: ToolInvocation) -> str:
    if invocation.action_request_id is None:
        return ""
    request = await connector.get(ActionRequest, invocation.action_request_id)
    if request is None:
        return ""
    return request.project.project_id
