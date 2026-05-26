"""MongoDB-backed domain persistence gateways."""

from collections.abc import Sequence
from typing import Any

from hoisa.adapters.persistence.mongodb.adapter import MongoAdapter
from hoisa.adapters.persistence.mongodb.collections import ASCENDING, DESCENDING
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
    LeaseLookupQuery,
    RepoLookup,
    RunnableWorkQuery,
    SourceObservationQuery,
    SyncCursorKey,
    ToolActionQuery,
    WaitingGateQuery,
)


class MongoCatalogGateway:
    def __init__(self, adapter: MongoAdapter) -> None:
        self._adapter = adapter

    async def save_project(self, project: Project) -> None:
        await self._adapter.upsert_entity(project)

    async def get_project(self, project_id: BsonObjectId) -> Project | None:
        return await self._adapter.find_one(Project, id=project_id)

    async def list_projects(self) -> Sequence[Project]:
        return await self._adapter.find_many(Project, sort=(("_id", ASCENDING),))

    async def save_target_repo(self, target_repo: TargetRepo) -> None:
        await self._adapter.upsert_entity(target_repo)

    async def get_target_repo(self, target_repo_id: BsonObjectId) -> TargetRepo | None:
        return await self._adapter.find_one(TargetRepo, id=target_repo_id)

    async def get_target_repo_by_provider(self, lookup: RepoLookup) -> TargetRepo | None:
        return await self._adapter.find_one(
            TargetRepo,
            query={
                "provider": lookup.provider,
                "owner": lookup.owner,
                "name": lookup.name,
            },
        )

    async def list_target_repos(self, project_id: BsonObjectId) -> Sequence[TargetRepo]:
        return await self._adapter.find_many(
            TargetRepo,
            query={"project.id": project_id},
            sort=(("_id", ASCENDING),),
        )


class MongoSourceGateway:
    def __init__(self, adapter: MongoAdapter) -> None:
        self._adapter = adapter

    async def save_connection(self, connection: SourceConnection) -> None:
        await self._adapter.upsert_entity(connection)

    async def get_connection(self, source_connection_id: BsonObjectId) -> SourceConnection | None:
        return await self._adapter.find_one(SourceConnection, id=source_connection_id)

    async def list_connections(self, project_id: BsonObjectId) -> Sequence[SourceConnection]:
        return await self._adapter.find_many(
            SourceConnection,
            query={"project.id": project_id},
            sort=(("_id", ASCENDING),),
        )

    async def save_observation(self, observation: SourceObservation) -> None:
        await self._adapter.upsert_entity(observation)

    async def get_observation(self, observation_id: BsonObjectId) -> SourceObservation | None:
        return await self._adapter.find_one(SourceObservation, id=observation_id)

    async def find_observations(self, query: SourceObservationQuery) -> Sequence[SourceObservation]:
        filter_query: dict[str, Any] = {"source_connection_id": query.source_connection_id}
        if query.external_id:
            filter_query["external_id"] = query.external_id
        if query.content_hash_value:
            filter_query["content_hash.value"] = query.content_hash_value
        return await self._adapter.find_many(
            SourceObservation,
            query=filter_query,
            sort=(("_id", ASCENDING),),
        )

    async def save_cursor(self, cursor: SyncCursor) -> None:
        await self._adapter.upsert_entity(cursor)

    async def get_cursor(self, key: SyncCursorKey) -> SyncCursor | None:
        return await self._adapter.find_one(
            SyncCursor,
            query={
                "source_connection_id": key.source_connection_id,
                "cursor_name": key.cursor_name,
            },
        )

    async def list_cursors(self, source_connection_id: BsonObjectId) -> Sequence[SyncCursor]:
        return await self._adapter.find_many(
            SyncCursor,
            query={"source_connection_id": source_connection_id},
            sort=(("_id", ASCENDING),),
        )


class MongoWorkflowGateway:
    def __init__(self, adapter: MongoAdapter) -> None:
        self._adapter = adapter

    async def save_work_item(self, work_item: WorkItem) -> None:
        await self._adapter.upsert_entity(work_item)

    async def get_work_item(self, work_item_id: BsonObjectId) -> WorkItem | None:
        return await self._adapter.find_one(WorkItem, id=work_item_id)

    async def find_work_item_by_tracker_issue(
        self, *, provider: str, issue_number: int
    ) -> WorkItem | None:
        return await self._adapter.find_one(
            WorkItem,
            query={
                "tracker_issue.provider": provider,
                "tracker_issue.issue_number": issue_number,
            },
        )

    async def find_runnable_work(self, query: RunnableWorkQuery) -> Sequence[WorkItem]:
        filter_query: dict[str, Any] = {}
        if query.project_id is not None:
            filter_query["target_repo.project.id"] = query.project_id
        if query.target_repo_id is not None:
            filter_query["target_repo.id"] = query.target_repo_id
        work_items = await self._adapter.find_many(
            WorkItem,
            query=filter_query,
            sort=(("created_at", ASCENDING), ("_id", ASCENDING)),
        )
        state_records = {
            record.work_item_id: record
            for record in await self._adapter.find_many(
                WorkflowStateRecord,
                query={"work_item_id": {"$in": [item.id for item in work_items]}},
            )
        }
        return tuple(
            sorted(
                (
                    work_item
                    for work_item in work_items
                    if self._is_runnable(work_item, state_records.get(work_item.id), query)
                ),
                key=lambda item: (item.created_at, str(item.id)),
            )
        )

    async def save_state(self, state_record: WorkflowStateRecord) -> None:
        await self._adapter.upsert_entity(state_record)

    async def get_state(self, work_item_id: BsonObjectId) -> WorkflowStateRecord | None:
        return await self._adapter.find_one(WorkflowStateRecord, id=work_item_id)

    async def list_states_by_worker(self, query: LeaseLookupQuery) -> Sequence[WorkflowStateRecord]:
        records = await self._adapter.find_many(
            WorkflowStateRecord,
            query=self._lease_worker_filter(query),
            sort=(("updated_at", ASCENDING), ("work_item_id", ASCENDING)),
        )
        return tuple(record for record in records if record.state.lease is not None)

    async def list_active_leases(self, query: LeaseLookupQuery) -> Sequence[WorkflowStateRecord]:
        records = await self._adapter.find_many(
            WorkflowStateRecord,
            query=self._lease_worker_filter(query),
            sort=(("updated_at", ASCENDING), ("work_item_id", ASCENDING)),
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
        records = await self._adapter.find_many(
            WorkflowStateRecord,
            query=self._lease_worker_filter(query),
            sort=(("updated_at", ASCENDING), ("work_item_id", ASCENDING)),
        )
        return tuple(
            record
            for record in records
            if record.state.lease is not None and record.state.lease.expires_at <= query.now
        )

    async def save_gate(self, gate: ApprovalGate) -> None:
        await self._adapter.upsert_entity(gate)

    async def get_gate(self, gate_id: BsonObjectId) -> ApprovalGate | None:
        return await self._adapter.find_one(ApprovalGate, id=gate_id)

    async def list_gates(self, work_item_id: BsonObjectId) -> Sequence[ApprovalGate]:
        return await self._adapter.find_many(
            ApprovalGate,
            query={"work_item_id": work_item_id},
            sort=(("created_at", ASCENDING), ("_id", ASCENDING)),
        )

    async def list_waiting_gates(self, query: WaitingGateQuery) -> Sequence[ApprovalGate]:
        filter_query: dict[str, Any] = {"gate_status": GateStatus.WAITING}
        if query.tracker_issue_number is not None:
            work_item_query: dict[str, Any] = {
                "tracker_issue.issue_number": query.tracker_issue_number
            }
            if query.work_item_id is not None:
                work_item_query["_id"] = query.work_item_id
            work_items = await self._adapter.find_many(WorkItem, query=work_item_query)
            work_item_ids = [work_item.id for work_item in work_items]
            if not work_item_ids:
                return ()
            filter_query["work_item_id"] = {"$in": work_item_ids}
        elif query.work_item_id is not None:
            filter_query["work_item_id"] = query.work_item_id
        return await self._adapter.find_many(
            ApprovalGate,
            query=filter_query,
            sort=(("created_at", ASCENDING), ("_id", ASCENDING)),
        )

    async def save_agent_run(self, run: AgentRun) -> None:
        await self._adapter.upsert_entity(run)

    async def get_agent_run(self, run_id: BsonObjectId) -> AgentRun | None:
        return await self._adapter.find_one(AgentRun, id=run_id)

    async def list_agent_runs(self, work_item_id: BsonObjectId) -> Sequence[AgentRun]:
        return await self._adapter.find_many(
            AgentRun,
            query={"work_item_id": work_item_id},
            sort=(("started_at", ASCENDING), ("_id", ASCENDING)),
        )

    def _is_runnable(
        self,
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
                or (not work_item.blocker_summaries and not self._has_active_blockers(blockers))
            )
            and (query.now is None or lease is None or lease.expires_at <= query.now)
        )

    def _has_active_blockers(self, blockers: Sequence[Blocker]) -> bool:
        return any(blocker.resolved_at is None for blocker in blockers)

    def _lease_worker_filter(self, query: LeaseLookupQuery) -> dict[str, Any]:
        if query.worker_id:
            return {"state.lease.worker_id": query.worker_id}
        return {"state.lease": {"$ne": None}}


class MongoEvidenceGateway:
    def __init__(self, adapter: MongoAdapter) -> None:
        self._adapter = adapter

    async def save_bundle(self, bundle: EvidenceBundle) -> None:
        await self._adapter.upsert_entity(bundle)

    async def get_bundle(self, bundle_id: BsonObjectId) -> EvidenceBundle | None:
        return await self._adapter.find_one(EvidenceBundle, id=bundle_id)

    async def list_bundles(
        self, *, subject_type: str, subject_id: BsonObjectId
    ) -> Sequence[EvidenceBundle]:
        return await self._adapter.find_many(
            EvidenceBundle,
            query={"subject_type": subject_type, "subject_id": subject_id},
            sort=(("_id", ASCENDING),),
        )


class MongoToolGateway:
    def __init__(self, adapter: MongoAdapter) -> None:
        self._adapter = adapter

    async def save_connection(self, connection: ToolConnection) -> None:
        await self._adapter.upsert_entity(connection)

    async def get_connection(self, tool_connection_id: BsonObjectId) -> ToolConnection | None:
        return await self._adapter.find_one(ToolConnection, id=tool_connection_id)

    async def list_connections(self, project_id: BsonObjectId) -> Sequence[ToolConnection]:
        return await self._adapter.find_many(
            ToolConnection,
            query={"project.id": project_id},
            sort=(("_id", ASCENDING),),
        )

    async def save_policy(self, policy: ToolPolicy) -> None:
        await self._adapter.upsert_entity(policy)

    async def get_policy(self, tool_policy_id: BsonObjectId) -> ToolPolicy | None:
        return await self._adapter.find_one(ToolPolicy, id=tool_policy_id)

    async def find_policies(self, query: ToolActionQuery) -> Sequence[ToolPolicy]:
        return await self._adapter.find_many(
            ToolPolicy,
            query=self._tool_action_filter(query),
            sort=(("_id", ASCENDING),),
        )

    async def save_action_request(self, request: ActionRequest) -> None:
        await self._adapter.upsert_entity(request)

    async def get_action_request(self, action_request_id: BsonObjectId) -> ActionRequest | None:
        return await self._adapter.find_one(ActionRequest, id=action_request_id)

    async def list_action_requests_by_status(
        self, status: ActionRequestStatus
    ) -> Sequence[ActionRequest]:
        return await self._adapter.find_many(
            ActionRequest,
            query={"status": status},
            sort=(("created_at", ASCENDING), ("_id", ASCENDING)),
        )

    async def list_action_requests_for_gate(self, gate_id: BsonObjectId) -> Sequence[ActionRequest]:
        return await self._adapter.find_many(
            ActionRequest,
            query={"required_gate_id": gate_id},
            sort=(("created_at", ASCENDING), ("_id", ASCENDING)),
        )

    async def save_invocation(self, invocation: ToolInvocation) -> None:
        await self._adapter.upsert_entity(invocation)

    async def get_invocation(self, tool_invocation_id: BsonObjectId) -> ToolInvocation | None:
        return await self._adapter.find_one(ToolInvocation, id=tool_invocation_id)

    async def list_invocations_for_action_request(
        self,
        action_request_id: BsonObjectId,
    ) -> Sequence[ToolInvocation]:
        return await self._adapter.find_many(
            ToolInvocation,
            query={"action_request_id": action_request_id},
            sort=(("happened_at", ASCENDING), ("_id", ASCENDING)),
        )

    async def list_invocations_by_tool_action(
        self,
        query: ToolActionQuery,
        *,
        status: ToolInvocationStatus | None = None,
    ) -> Sequence[ToolInvocation]:
        filter_query = self._tool_action_filter(query)
        filter_query.pop("project.id", None)
        if status is not None:
            filter_query["status"] = status
        if query.project_id is not None:
            requests = await self._adapter.find_many(
                ActionRequest,
                query={"project.id": query.project_id},
            )
            action_request_ids = [request.id for request in requests]
            if not action_request_ids:
                return ()
            filter_query["action_request_id"] = {"$in": action_request_ids}
        return await self._adapter.find_many(
            ToolInvocation,
            query=filter_query,
            sort=(("happened_at", ASCENDING), ("_id", ASCENDING)),
        )

    def _tool_action_filter(self, query: ToolActionQuery) -> dict[str, Any]:
        filter_query: dict[str, Any] = {}
        if query.tool_type:
            filter_query["tool_type"] = query.tool_type
        if query.action_type:
            filter_query["action_type"] = query.action_type
        if query.project_id is not None:
            filter_query["project.id"] = query.project_id
        return filter_query


class MongoEventGateway:
    def __init__(self, adapter: MongoAdapter) -> None:
        self._adapter = adapter

    async def append(self, event: WorkflowEvent) -> None:
        await self._adapter.insert_entity(event)

    async def get(self, event_id: BsonObjectId) -> WorkflowEvent | None:
        return await self._adapter.find_one(WorkflowEvent, id=event_id)

    async def list_for_subject(self, subject: EventSubject) -> Sequence[WorkflowEvent]:
        return await self._adapter.find_many(
            WorkflowEvent,
            query={
                "subject.subject_type": subject.subject_type,
                "subject.subject_id": subject.subject_id,
            },
            sort=(("happened_at", ASCENDING), ("_id", ASCENDING)),
        )

    async def list_for_correlation(self, correlation_id: str) -> Sequence[WorkflowEvent]:
        return await self._adapter.find_many(
            WorkflowEvent,
            query={"correlation_id": correlation_id},
            sort=(("happened_at", ASCENDING), ("_id", ASCENDING)),
        )

    async def list_recent(self, *, limit: int) -> Sequence[WorkflowEvent]:
        if limit <= 0:
            return ()
        events = await self._adapter.find_many(
            WorkflowEvent,
            sort=(("happened_at", DESCENDING), ("_id", DESCENDING)),
            limit=limit,
        )
        return tuple(reversed(events))
