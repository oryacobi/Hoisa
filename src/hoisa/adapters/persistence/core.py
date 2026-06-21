"""Shared generic persistence helpers for Hoisa document stores."""

from collections.abc import Mapping, Sequence
from typing import Any, Protocol, cast

from antonic import AntDoc

from hoisa.domain.directives import Directive
from hoisa.domain.events import EventSubject, WorkflowEvent
from hoisa.domain.evidence import EvidenceBundle
from hoisa.domain.gates import ApprovalGate, GateStatus
from hoisa.domain.models import ASCENDING, RecordId
from hoisa.domain.runs import AgentRun
from hoisa.domain.sources import SourceConnection, SourceObservation, SyncCursor
from hoisa.domain.target_repos import Project, TargetRepo
from hoisa.domain.task_packets import TaskPacket
from hoisa.domain.tool_control import (
    ActionRequest,
    ToolConnection,
    ToolInvocation,
    ToolInvocationStatus,
    ToolPolicy,
)
from hoisa.domain.work_items import WorkItem
from hoisa.domain.workflow_state import Blocker, WorkflowStateRecord
from hoisa.ports.persistence import (
    DuplicateRecordError,
    LeaseLookupQuery,
    RunnableWorkQuery,
    ToolActionQuery,
    WaitingGateQuery,
)

DURABLE_RECORD_TYPES: tuple[type[AntDoc], ...] = (
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
_SORT_BY_HAPPENED_ID = [("happened_at", ASCENDING), ("id", ASCENDING)]


class _GenericStore(Protocol):
    async def insert[T: AntDoc](self, ant_doc: T) -> T: ...

    async def get[T: AntDoc](
        self,
        doc_type: type[T],
        id: Any = None,
        filter: Mapping[str, Any] | None = None,
        *,
        sort: Any = None,
        **where: Any,
    ) -> T | None: ...

    async def find[T: AntDoc](
        self,
        doc_type: type[T],
        filter: Mapping[str, Any] | None = None,
        *,
        sort: Any = None,
        limit: int | None = None,
        **where: Any,
    ) -> list[T]: ...


class HoisaPersistenceHelpers:
    """Workflow-specific queries over an Antonic-style generic store."""

    def _store(self) -> _GenericStore:
        return cast(_GenericStore, self)

    async def append_event(self, event: WorkflowEvent) -> WorkflowEvent:
        store = self._store()
        if event.id is not None and await store.get(WorkflowEvent, event.id) is not None:
            raise DuplicateRecordError(f"Workflow event already exists: {event.id}")
        return await store.insert(event)

    async def find_runnable_work(self, query: RunnableWorkQuery) -> tuple[WorkItem, ...]:
        store = self._store()
        items = await store.find(WorkItem, sort=_SORT_BY_CREATED_ID)
        runnable: list[WorkItem] = []
        for item in items:
            state = await store.get(WorkflowStateRecord, item.id)
            if _is_runnable(item, state, query):
                runnable.append(item)
        return tuple(runnable)

    async def list_workflow_states_by_worker(
        self, query: LeaseLookupQuery
    ) -> tuple[WorkflowStateRecord, ...]:
        return tuple(
            await self._store().find(
                WorkflowStateRecord,
                filter=_worker_filter(query),
                sort=_SORT_BY_UPDATED_ID,
            )
        )

    async def list_active_leases(self, query: LeaseLookupQuery) -> tuple[WorkflowStateRecord, ...]:
        records = await self.list_workflow_states_by_worker(query)
        return tuple(
            record
            for record in records
            if record.state.lease is not None
            and (query.now is None or record.state.lease.expires_at > query.now)
        )

    async def list_expired_leases(self, query: LeaseLookupQuery) -> tuple[WorkflowStateRecord, ...]:
        if query.now is None:
            return ()
        records = await self.list_workflow_states_by_worker(query)
        return tuple(
            record
            for record in records
            if record.state.lease is not None and record.state.lease.expires_at <= query.now
        )

    async def list_waiting_gates(self, query: WaitingGateQuery) -> tuple[ApprovalGate, ...]:
        filters: dict[str, Any] = {"gate_status": GateStatus.WAITING}
        if query.work_item_id is not None:
            filters["work_item_id"] = query.work_item_id
        gates = await self._store().find(ApprovalGate, filter=filters, sort=_SORT_BY_CREATED_ID)
        if query.tracker_issue_number is None:
            return tuple(gates)

        waiting: list[ApprovalGate] = []
        for gate in gates:
            work_item = await self._store().get(WorkItem, gate.work_item_id)
            if (
                work_item is not None
                and work_item.tracker_issue is not None
                and work_item.tracker_issue.issue_number == query.tracker_issue_number
            ):
                waiting.append(gate)
        return tuple(waiting)

    async def list_tool_policies_for_action(self, query: ToolActionQuery) -> tuple[ToolPolicy, ...]:
        return tuple(
            await self._store().find(
                ToolPolicy,
                filter=_tool_action_filter(query),
                sort=_SORT_BY_ID,
            )
        )

    async def list_tool_invocations_by_action(
        self,
        query: ToolActionQuery,
        *,
        status: ToolInvocationStatus | None = None,
    ) -> tuple[ToolInvocation, ...]:
        filters: dict[str, Any] = {
            key: value
            for key, value in {
                "tool_type": query.tool_type,
                "action_type": query.action_type,
                "status": status,
            }.items()
            if value
        }
        invocations = await self._store().find(
            ToolInvocation,
            filter=filters,
            sort=_SORT_BY_HAPPENED_ID,
        )
        if query.project_id is None:
            return tuple(invocations)

        matched: list[ToolInvocation] = []
        for invocation in invocations:
            if await _invocation_project_id(self._store(), invocation) == query.project_id:
                matched.append(invocation)
        return tuple(matched)

    async def list_events_for_subject(self, subject: EventSubject) -> tuple[WorkflowEvent, ...]:
        return tuple(
            await self._store().find(
                WorkflowEvent,
                filter={
                    "subject.subject_type": subject.subject_type,
                    "subject.subject_id": subject.subject_id,
                },
                sort=_SORT_BY_HAPPENED_ID,
            )
        )

    async def list_events_for_correlation(self, correlation_id: str) -> tuple[WorkflowEvent, ...]:
        return tuple(
            await self._store().find(
                WorkflowEvent,
                filter={"correlation_id": correlation_id},
                sort=_SORT_BY_HAPPENED_ID,
            )
        )

    async def list_recent_events(self, *, limit: int) -> tuple[WorkflowEvent, ...]:
        if limit <= 0:
            return ()
        events = await self._store().find(WorkflowEvent, sort=_SORT_BY_HAPPENED_ID)
        return tuple(events[-limit:])


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
        if value is not None and value != ""
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
        and (
            query.project_id is None or work_item.target_repo.project.project_id == query.project_id
        )
        and (
            query.target_repo_id is None
            or work_item.target_repo.target_repo_id == query.target_repo_id
        )
        and (
            query.include_blocked
            or (not work_item.blocker_summaries and not _has_active_blockers(blockers))
        )
        and (query.now is None or lease is None or lease.expires_at <= query.now)
    )


def _has_active_blockers(blockers: Sequence[Blocker]) -> bool:
    return any(blocker.resolved_at is None for blocker in blockers)


async def _invocation_project_id(
    store: _GenericStore, invocation: ToolInvocation
) -> RecordId | None:
    if invocation.action_request_id is None:
        return None
    request = await store.get(ActionRequest, invocation.action_request_id)
    if request is None:
        return None
    return request.project.project_id
