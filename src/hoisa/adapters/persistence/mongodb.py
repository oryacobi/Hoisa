"""MongoDB persistence adapter for Hoisa repositories and events."""

from collections.abc import Awaitable, Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import Enum
from inspect import isawaitable
from typing import Any, Self, cast

from bson.codec_options import CodecOptions
from pydantic import BaseModel
from pymongo import AsyncMongoClient, IndexModel
from pymongo.errors import DuplicateKeyError, PyMongoError

from hoisa.domain.events import EventSubject, WorkflowEvent
from hoisa.domain.evidence import EvidenceBundle
from hoisa.domain.gates import ApprovalGate, GateStatus
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
    PersistenceError,
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

Document = dict[str, Any]
Filter = Mapping[str, Any]
SortKey = tuple[str, int]
ASCENDING = 1


@dataclass(frozen=True, slots=True)
class MongoPersistenceConfig:
    """Configuration for the MongoDB persistence provider."""

    database_name: str
    server_selection_timeout_ms: int = 2000


@dataclass(frozen=True, slots=True)
class MongoIndexSpec:
    """Adapter-owned MongoDB index declaration."""

    name: str
    keys: tuple[SortKey, ...]
    unique: bool = False
    partial_filter_expression: Mapping[str, Any] | None = None


@dataclass(frozen=True, slots=True)
class MongoCollectionSpec:
    """Explicit collection mapping for a persisted Hoisa record type."""

    collection_name: str
    id_field: str
    model_type: type[BaseModel]
    duplicate_label: str
    indexes: tuple[MongoIndexSpec, ...] = ()


MONGO_COLLECTION_SPECS: tuple[MongoCollectionSpec, ...] = (
    MongoCollectionSpec(
        collection_name="projects",
        id_field="project_id",
        model_type=Project,
        duplicate_label="project",
        indexes=(MongoIndexSpec(name="project_id_lookup", keys=(("project_id", ASCENDING),)),),
    ),
    MongoCollectionSpec(
        collection_name="target_repos",
        id_field="target_repo_id",
        model_type=TargetRepo,
        duplicate_label="target repository",
        indexes=(
            MongoIndexSpec(
                name="provider_owner_name_unique",
                keys=(("provider", ASCENDING), ("owner", ASCENDING), ("name", ASCENDING)),
                unique=True,
            ),
            MongoIndexSpec(
                name="project_repo_lookup",
                keys=(("project.project_id", ASCENDING), ("target_repo_id", ASCENDING)),
            ),
        ),
    ),
    MongoCollectionSpec(
        collection_name="source_connections",
        id_field="source_connection_id",
        model_type=SourceConnection,
        duplicate_label="source connection",
        indexes=(
            MongoIndexSpec(
                name="project_target_source_status_lookup",
                keys=(
                    ("project.project_id", ASCENDING),
                    ("target_repo.target_repo_id", ASCENDING),
                    ("source_system", ASCENDING),
                    ("status", ASCENDING),
                ),
            ),
        ),
    ),
    MongoCollectionSpec(
        collection_name="source_observations",
        id_field="observation_id",
        model_type=SourceObservation,
        duplicate_label="source observation",
        indexes=(
            MongoIndexSpec(
                name="source_external_hash_unique",
                keys=(
                    ("source_connection_id", ASCENDING),
                    ("external_id", ASCENDING),
                    ("content_hash.value", ASCENDING),
                ),
                unique=True,
            ),
            MongoIndexSpec(
                name="source_external_hash_lookup",
                keys=(
                    ("source_connection_id", ASCENDING),
                    ("external_id", ASCENDING),
                    ("content_hash.value", ASCENDING),
                ),
            ),
        ),
    ),
    MongoCollectionSpec(
        collection_name="sync_cursors",
        id_field="cursor_id",
        model_type=SyncCursor,
        duplicate_label="sync cursor",
        indexes=(
            MongoIndexSpec(
                name="source_cursor_unique",
                keys=(("source_connection_id", ASCENDING), ("cursor_name", ASCENDING)),
                unique=True,
            ),
            MongoIndexSpec(
                name="source_cursor_lookup",
                keys=(("source_connection_id", ASCENDING), ("cursor_name", ASCENDING)),
            ),
        ),
    ),
    MongoCollectionSpec(
        collection_name="work_items",
        id_field="work_item_id",
        model_type=WorkItem,
        duplicate_label="work item tracker issue",
        indexes=(
            MongoIndexSpec(
                name="tracker_issue_unique",
                keys=(
                    ("tracker_issue.provider", ASCENDING),
                    ("tracker_issue.issue_number", ASCENDING),
                ),
                unique=True,
                partial_filter_expression={"tracker_issue": {"$exists": True}},
            ),
            MongoIndexSpec(
                name="project_target_lookup",
                keys=(
                    ("target_repo.project.project_id", ASCENDING),
                    ("target_repo.target_repo_id", ASCENDING),
                ),
            ),
            MongoIndexSpec(
                name="workflow_stage_status_risk_created_lookup",
                keys=(
                    ("workflow_stage", ASCENDING),
                    ("status", ASCENDING),
                    ("risk", ASCENDING),
                    ("created_at", ASCENDING),
                    ("work_item_id", ASCENDING),
                ),
            ),
        ),
    ),
    MongoCollectionSpec(
        collection_name="workflow_states",
        id_field="work_item_id",
        model_type=WorkflowStateRecord,
        duplicate_label="workflow state",
        indexes=(
            MongoIndexSpec(
                name="stage_status_risk_lookup",
                keys=(
                    ("state.stage", ASCENDING),
                    ("state.status", ASCENDING),
                    ("state.risk", ASCENDING),
                ),
            ),
            MongoIndexSpec(
                name="lease_worker_expiration_lookup",
                keys=(
                    ("state.lease.worker_id", ASCENDING),
                    ("state.lease.expires_at", ASCENDING),
                ),
            ),
            MongoIndexSpec(
                name="updated_work_item_lookup",
                keys=(("updated_at", ASCENDING), ("work_item_id", ASCENDING)),
            ),
        ),
    ),
    MongoCollectionSpec(
        collection_name="approval_gates",
        id_field="gate_id",
        model_type=ApprovalGate,
        duplicate_label="approval gate",
        indexes=(
            MongoIndexSpec(
                name="work_item_status_stage_lookup",
                keys=(
                    ("work_item_id", ASCENDING),
                    ("gate_status", ASCENDING),
                    ("workflow_stage", ASCENDING),
                ),
            ),
            MongoIndexSpec(
                name="status_created_lookup",
                keys=(
                    ("gate_status", ASCENDING),
                    ("created_at", ASCENDING),
                    ("gate_id", ASCENDING),
                ),
            ),
        ),
    ),
    MongoCollectionSpec(
        collection_name="agent_runs",
        id_field="run_id",
        model_type=AgentRun,
        duplicate_label="agent run",
        indexes=(
            MongoIndexSpec(
                name="work_item_stage_started_lookup",
                keys=(
                    ("work_item_id", ASCENDING),
                    ("workflow_stage", ASCENDING),
                    ("started_at", ASCENDING),
                    ("run_id", ASCENDING),
                ),
            ),
        ),
    ),
    MongoCollectionSpec(
        collection_name="evidence_bundles",
        id_field="bundle_id",
        model_type=EvidenceBundle,
        duplicate_label="evidence bundle",
        indexes=(
            MongoIndexSpec(
                name="subject_lookup",
                keys=(
                    ("subject_type", ASCENDING),
                    ("subject_id", ASCENDING),
                    ("bundle_id", ASCENDING),
                ),
            ),
        ),
    ),
    MongoCollectionSpec(
        collection_name="tool_connections",
        id_field="tool_connection_id",
        model_type=ToolConnection,
        duplicate_label="tool connection",
        indexes=(
            MongoIndexSpec(
                name="project_tool_status_lookup",
                keys=(
                    ("project.project_id", ASCENDING),
                    ("tool_type", ASCENDING),
                    ("status", ASCENDING),
                ),
            ),
        ),
    ),
    MongoCollectionSpec(
        collection_name="tool_policies",
        id_field="tool_policy_id",
        model_type=ToolPolicy,
        duplicate_label="tool policy",
        indexes=(
            MongoIndexSpec(
                name="project_tool_action_unique",
                keys=(
                    ("project.project_id", ASCENDING),
                    ("tool_type", ASCENDING),
                    ("action_type", ASCENDING),
                ),
                unique=True,
            ),
            MongoIndexSpec(
                name="project_tool_action_lookup",
                keys=(
                    ("project.project_id", ASCENDING),
                    ("tool_type", ASCENDING),
                    ("action_type", ASCENDING),
                ),
            ),
        ),
    ),
    MongoCollectionSpec(
        collection_name="action_requests",
        id_field="action_request_id",
        model_type=ActionRequest,
        duplicate_label="action request",
        indexes=(
            MongoIndexSpec(
                name="status_gate_created_lookup",
                keys=(
                    ("status", ASCENDING),
                    ("required_gate_id", ASCENDING),
                    ("created_at", ASCENDING),
                ),
            ),
            MongoIndexSpec(
                name="project_tool_action_lookup",
                keys=(
                    ("project.project_id", ASCENDING),
                    ("tool_type", ASCENDING),
                    ("action_type", ASCENDING),
                ),
            ),
        ),
    ),
    MongoCollectionSpec(
        collection_name="tool_invocations",
        id_field="tool_invocation_id",
        model_type=ToolInvocation,
        duplicate_label="tool invocation",
        indexes=(
            MongoIndexSpec(
                name="action_request_happened_lookup",
                keys=(("action_request_id", ASCENDING), ("happened_at", ASCENDING)),
            ),
            MongoIndexSpec(
                name="tool_action_status_happened_lookup",
                keys=(
                    ("tool_type", ASCENDING),
                    ("action_type", ASCENDING),
                    ("status", ASCENDING),
                    ("happened_at", ASCENDING),
                ),
            ),
        ),
    ),
    MongoCollectionSpec(
        collection_name="workflow_events",
        id_field="event_id",
        model_type=WorkflowEvent,
        duplicate_label="Workflow event",
        indexes=(
            MongoIndexSpec(
                name="subject_happened_lookup",
                keys=(
                    ("subject.subject_type", ASCENDING),
                    ("subject.subject_id", ASCENDING),
                    ("happened_at", ASCENDING),
                    ("event_id", ASCENDING),
                ),
            ),
            MongoIndexSpec(
                name="correlation_happened_lookup",
                keys=(
                    ("correlation_id", ASCENDING),
                    ("happened_at", ASCENDING),
                    ("event_id", ASCENDING),
                ),
            ),
            MongoIndexSpec(
                name="happened_lookup",
                keys=(("happened_at", ASCENDING), ("event_id", ASCENDING)),
            ),
        ),
    ),
)

_SPECS_BY_COLLECTION = {spec.collection_name: spec for spec in MONGO_COLLECTION_SPECS}


class MongoPersistenceProvider(PersistenceProvider):
    """MongoDB implementation of all persistence repositories."""

    def __init__(
        self,
        client: AsyncMongoClient[Document],
        *,
        database_name: str,
    ) -> None:
        self._client = client
        self.database_name = database_name
        codec_options: CodecOptions[Document] = CodecOptions(tz_aware=True, tzinfo=UTC)
        self._database = client.get_database(database_name, codec_options=codec_options)
        self._projects = _MongoProjectRepository(self)
        self._target_repos = _MongoTargetRepoRepository(self)
        self._source_connections = _MongoSourceConnectionRepository(self)
        self._source_observations = _MongoSourceObservationRepository(self)
        self._sync_cursors = _MongoSyncCursorRepository(self)
        self._work_items = _MongoWorkItemRepository(self)
        self._workflow_states = _MongoWorkflowStateRepository(self)
        self._gates = _MongoApprovalGateRepository(self)
        self._agent_runs = _MongoAgentRunRepository(self)
        self._evidence_bundles = _MongoEvidenceBundleRepository(self)
        self._tool_connections = _MongoToolConnectionRepository(self)
        self._tool_policies = _MongoToolPolicyRepository(self)
        self._action_requests = _MongoActionRequestRepository(self)
        self._tool_invocations = _MongoToolInvocationRepository(self)
        self._workflow_events = _MongoWorkflowEventStore(self)

    @classmethod
    def from_uri(
        cls,
        uri: str,
        *,
        database_name: str,
        server_selection_timeout_ms: int = 2000,
    ) -> Self:
        """Create a provider from a MongoDB URI without exposing it through ports."""

        client: AsyncMongoClient[Document] = AsyncMongoClient(
            uri,
            serverSelectionTimeoutMS=server_selection_timeout_ms,
        )
        return cls(client, database_name=database_name)

    async def ensure_indexes(self) -> None:
        """Create all adapter-owned MongoDB indexes."""

        try:
            for spec in MONGO_COLLECTION_SPECS:
                models = [
                    _index_model(index_spec)
                    for index_spec in spec.indexes
                    if index_spec.keys != (("_id", ASCENDING),)
                ]
                if models:
                    await self._collection(spec.collection_name).create_indexes(models)
        except PyMongoError as exc:
            raise PersistenceError("Failed to ensure MongoDB persistence indexes.") from exc

    async def close(self) -> None:
        """Close the underlying MongoDB client."""

        result = self._client.close()
        if isawaitable(result):
            await cast(Awaitable[None], result)

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

    def _collection(self, collection_name: str) -> Any:
        return self._database.get_collection(collection_name)


class _MongoRecordRepository[T: BaseModel]:
    def __init__(self, provider: MongoPersistenceProvider, collection_name: str) -> None:
        self._provider = provider
        self._spec = _SPECS_BY_COLLECTION[collection_name]
        self._collection_name = collection_name
        self._model_type = cast(type[T], self._spec.model_type)

    @property
    def _collection(self) -> Any:
        return self._provider._collection(self._collection_name)

    async def _save(self, record: T) -> None:
        document = _document_for_model(record, self._spec.id_field)
        try:
            await self._collection.replace_one(
                {"_id": document["_id"]},
                document,
                upsert=True,
            )
        except DuplicateKeyError as exc:
            raise DuplicateRecordError(f"Duplicate {self._spec.duplicate_label}.") from exc
        except PyMongoError as exc:
            raise PersistenceError(f"Failed to save {self._spec.duplicate_label}.") from exc

    async def _insert(self, record: T) -> None:
        document = _document_for_model(record, self._spec.id_field)
        try:
            await self._collection.insert_one(document)
        except DuplicateKeyError as exc:
            raise DuplicateRecordError(f"{self._spec.duplicate_label} already exists.") from exc
        except PyMongoError as exc:
            raise PersistenceError(f"Failed to append {self._spec.duplicate_label}.") from exc

    async def _get(self, stable_id: str) -> T | None:
        return await self._find_one({"_id": stable_id})

    async def _find_one(self, filter_query: Filter) -> T | None:
        try:
            document = await self._collection.find_one(dict(filter_query))
        except PyMongoError as exc:
            raise PersistenceError(f"Failed to read {self._spec.duplicate_label}.") from exc
        if document is None:
            return None
        return _model_from_document(self._model_type, cast(Mapping[str, Any], document))

    async def _find_many(self, filter_query: Filter | None = None) -> tuple[T, ...]:
        try:
            cursor = self._collection.find(dict(filter_query or {}))
            documents = await cursor.to_list(length=None)
        except PyMongoError as exc:
            raise PersistenceError(f"Failed to list {self._spec.duplicate_label}.") from exc
        return tuple(
            _model_from_document(self._model_type, cast(Mapping[str, Any], document))
            for document in documents
        )


class _MongoProjectRepository(_MongoRecordRepository[Project]):
    def __init__(self, provider: MongoPersistenceProvider) -> None:
        super().__init__(provider, "projects")

    async def save(self, project: Project) -> None:
        await self._save(project)

    async def get(self, project_id: str) -> Project | None:
        return await self._get(project_id)

    async def list_all(self) -> Sequence[Project]:
        return _sorted_by_id(await self._find_many(), lambda project: project.project_id)


class _MongoTargetRepoRepository(_MongoRecordRepository[TargetRepo]):
    def __init__(self, provider: MongoPersistenceProvider) -> None:
        super().__init__(provider, "target_repos")

    async def save(self, target_repo: TargetRepo) -> None:
        await self._save(target_repo)

    async def get(self, target_repo_id: str) -> TargetRepo | None:
        return await self._get(target_repo_id)

    async def get_by_provider(self, lookup: RepoLookup) -> TargetRepo | None:
        return await self._find_one(
            {
                "provider": lookup.provider.value,
                "owner": lookup.owner,
                "name": lookup.name,
            }
        )

    async def list_by_project(self, project_id: str) -> Sequence[TargetRepo]:
        return _sorted_by_id(
            await self._find_many({"project.project_id": project_id}),
            lambda repo: repo.target_repo_id,
        )


class _MongoSourceConnectionRepository(_MongoRecordRepository[SourceConnection]):
    def __init__(self, provider: MongoPersistenceProvider) -> None:
        super().__init__(provider, "source_connections")

    async def save(self, connection: SourceConnection) -> None:
        await self._save(connection)

    async def get(self, source_connection_id: str) -> SourceConnection | None:
        return await self._get(source_connection_id)

    async def list_by_project(self, project_id: str) -> Sequence[SourceConnection]:
        return _sorted_by_id(
            await self._find_many({"project.project_id": project_id}),
            lambda connection: connection.source_connection_id,
        )


class _MongoSourceObservationRepository(_MongoRecordRepository[SourceObservation]):
    def __init__(self, provider: MongoPersistenceProvider) -> None:
        super().__init__(provider, "source_observations")

    async def save(self, observation: SourceObservation) -> None:
        await self._save(observation)

    async def get(self, observation_id: str) -> SourceObservation | None:
        return await self._get(observation_id)

    async def find_by_source(self, query: SourceObservationQuery) -> Sequence[SourceObservation]:
        filter_query: dict[str, Any] = {"source_connection_id": query.source_connection_id}
        if query.external_id:
            filter_query["external_id"] = query.external_id
        if query.content_hash_value:
            filter_query["content_hash.value"] = query.content_hash_value
        return _sorted_by_id(
            await self._find_many(filter_query),
            lambda observation: observation.observation_id,
        )


class _MongoSyncCursorRepository(_MongoRecordRepository[SyncCursor]):
    def __init__(self, provider: MongoPersistenceProvider) -> None:
        super().__init__(provider, "sync_cursors")

    async def save(self, cursor: SyncCursor) -> None:
        await self._save(cursor)

    async def get(self, key: SyncCursorKey) -> SyncCursor | None:
        return await self._find_one(
            {
                "source_connection_id": key.source_connection_id,
                "cursor_name": key.cursor_name,
            }
        )

    async def list_by_source(self, source_connection_id: str) -> Sequence[SyncCursor]:
        return _sorted_by_id(
            await self._find_many({"source_connection_id": source_connection_id}),
            lambda cursor: cursor.cursor_id,
        )


class _MongoWorkItemRepository(_MongoRecordRepository[WorkItem]):
    def __init__(self, provider: MongoPersistenceProvider) -> None:
        super().__init__(provider, "work_items")
        self._workflow_states = _MongoWorkflowStateRepository(provider)

    async def save(self, work_item: WorkItem) -> None:
        await self._save(work_item)

    async def get(self, work_item_id: str) -> WorkItem | None:
        return await self._get(work_item_id)

    async def find_by_tracker_issue(self, *, provider: str, issue_number: int) -> WorkItem | None:
        return await self._find_one(
            {
                "tracker_issue.provider": provider,
                "tracker_issue.issue_number": issue_number,
            }
        )

    async def find_runnable(self, query: RunnableWorkQuery) -> Sequence[WorkItem]:
        filter_query: dict[str, Any] = {}
        if query.project_id:
            filter_query["target_repo.project.project_id"] = query.project_id
        if query.target_repo_id:
            filter_query["target_repo.target_repo_id"] = query.target_repo_id
        work_items = await self._find_many(filter_query)
        state_records = {
            record.work_item_id: record
            for record in await self._workflow_states._find_many()
            if record.work_item_id in {item.work_item_id for item in work_items}
        }
        return _sorted_work_items(
            work_item
            for work_item in work_items
            if _is_runnable(work_item, state_records.get(work_item.work_item_id), query)
        )


class _MongoWorkflowStateRepository(_MongoRecordRepository[WorkflowStateRecord]):
    def __init__(self, provider: MongoPersistenceProvider) -> None:
        super().__init__(provider, "workflow_states")

    async def save(self, state_record: WorkflowStateRecord) -> None:
        await self._save(state_record)

    async def get(self, work_item_id: str) -> WorkflowStateRecord | None:
        return await self._get(work_item_id)

    async def list_by_worker(self, query: LeaseLookupQuery) -> Sequence[WorkflowStateRecord]:
        records = await self._find_many(_lease_worker_filter(query))
        return _sorted_state_records(record for record in records if record.state.lease is not None)

    async def list_active_leases(self, query: LeaseLookupQuery) -> Sequence[WorkflowStateRecord]:
        records = await self._find_many(_lease_worker_filter(query))
        return _sorted_state_records(
            record
            for record in records
            if record.state.lease is not None
            and (query.now is None or record.state.lease.expires_at > query.now)
        )

    async def list_expired_leases(self, query: LeaseLookupQuery) -> Sequence[WorkflowStateRecord]:
        if query.now is None:
            return ()
        records = await self._find_many(_lease_worker_filter(query))
        return _sorted_state_records(
            record
            for record in records
            if record.state.lease is not None and record.state.lease.expires_at <= query.now
        )


class _MongoApprovalGateRepository(_MongoRecordRepository[ApprovalGate]):
    def __init__(self, provider: MongoPersistenceProvider) -> None:
        super().__init__(provider, "approval_gates")
        self._work_items = _MongoWorkItemRepository(provider)

    async def save(self, gate: ApprovalGate) -> None:
        await self._save(gate)

    async def get(self, gate_id: str) -> ApprovalGate | None:
        return await self._get(gate_id)

    async def list_by_work_item(self, work_item_id: str) -> Sequence[ApprovalGate]:
        return _sorted_gates(
            await self._find_many({"work_item_id": work_item_id}),
        )

    async def list_waiting(self, query: WaitingGateQuery) -> Sequence[ApprovalGate]:
        filter_query: dict[str, Any] = {"gate_status": GateStatus.WAITING.value}
        if query.work_item_id:
            filter_query["work_item_id"] = query.work_item_id
        gates = await self._find_many(filter_query)
        if query.tracker_issue_number is None:
            return _sorted_gates(gates)
        matched: list[ApprovalGate] = []
        for gate in gates:
            work_item = await self._work_items.get(gate.work_item_id)
            if (
                work_item is not None
                and work_item.tracker_issue is not None
                and work_item.tracker_issue.issue_number == query.tracker_issue_number
            ):
                matched.append(gate)
        return _sorted_gates(matched)


class _MongoAgentRunRepository(_MongoRecordRepository[AgentRun]):
    def __init__(self, provider: MongoPersistenceProvider) -> None:
        super().__init__(provider, "agent_runs")

    async def save(self, run: AgentRun) -> None:
        await self._save(run)

    async def get(self, run_id: str) -> AgentRun | None:
        return await self._get(run_id)

    async def list_by_work_item(self, work_item_id: str) -> Sequence[AgentRun]:
        return _sorted_by_id(
            await self._find_many({"work_item_id": work_item_id}),
            lambda run: run.run_id,
        )


class _MongoEvidenceBundleRepository(_MongoRecordRepository[EvidenceBundle]):
    def __init__(self, provider: MongoPersistenceProvider) -> None:
        super().__init__(provider, "evidence_bundles")

    async def save(self, bundle: EvidenceBundle) -> None:
        await self._save(bundle)

    async def get(self, bundle_id: str) -> EvidenceBundle | None:
        return await self._get(bundle_id)

    async def list_by_subject(
        self, *, subject_type: str, subject_id: str
    ) -> Sequence[EvidenceBundle]:
        return _sorted_by_id(
            await self._find_many({"subject_type": subject_type, "subject_id": subject_id}),
            lambda bundle: bundle.bundle_id,
        )


class _MongoToolConnectionRepository(_MongoRecordRepository[ToolConnection]):
    def __init__(self, provider: MongoPersistenceProvider) -> None:
        super().__init__(provider, "tool_connections")

    async def save(self, connection: ToolConnection) -> None:
        await self._save(connection)

    async def get(self, tool_connection_id: str) -> ToolConnection | None:
        return await self._get(tool_connection_id)

    async def list_by_project(self, project_id: str) -> Sequence[ToolConnection]:
        return _sorted_by_id(
            await self._find_many({"project.project_id": project_id}),
            lambda connection: connection.tool_connection_id,
        )


class _MongoToolPolicyRepository(_MongoRecordRepository[ToolPolicy]):
    def __init__(self, provider: MongoPersistenceProvider) -> None:
        super().__init__(provider, "tool_policies")

    async def save(self, policy: ToolPolicy) -> None:
        await self._save(policy)

    async def get(self, tool_policy_id: str) -> ToolPolicy | None:
        return await self._get(tool_policy_id)

    async def find_for_action(self, query: ToolActionQuery) -> Sequence[ToolPolicy]:
        return _sorted_by_id(
            await self._find_many(_tool_action_filter(query)),
            lambda policy: policy.tool_policy_id,
        )


class _MongoActionRequestRepository(_MongoRecordRepository[ActionRequest]):
    def __init__(self, provider: MongoPersistenceProvider) -> None:
        super().__init__(provider, "action_requests")

    async def save(self, request: ActionRequest) -> None:
        await self._save(request)

    async def get(self, action_request_id: str) -> ActionRequest | None:
        return await self._get(action_request_id)

    async def list_by_status(self, status: ActionRequestStatus) -> Sequence[ActionRequest]:
        return _sorted_by_id(
            await self._find_many({"status": status.value}),
            lambda request: request.action_request_id,
        )

    async def list_for_gate(self, gate_id: str) -> Sequence[ActionRequest]:
        return _sorted_by_id(
            await self._find_many({"required_gate_id": gate_id}),
            lambda request: request.action_request_id,
        )


class _MongoToolInvocationRepository(_MongoRecordRepository[ToolInvocation]):
    def __init__(self, provider: MongoPersistenceProvider) -> None:
        super().__init__(provider, "tool_invocations")
        self._action_requests = _MongoActionRequestRepository(provider)

    async def save(self, invocation: ToolInvocation) -> None:
        await self._save(invocation)

    async def get(self, tool_invocation_id: str) -> ToolInvocation | None:
        return await self._get(tool_invocation_id)

    async def list_for_action_request(self, action_request_id: str) -> Sequence[ToolInvocation]:
        return _sorted_invocations(
            await self._find_many({"action_request_id": action_request_id}),
        )

    async def list_by_tool_action(
        self,
        query: ToolActionQuery,
        *,
        status: ToolInvocationStatus | None = None,
    ) -> Sequence[ToolInvocation]:
        filter_query: dict[str, Any] = {}
        if query.tool_type:
            filter_query["tool_type"] = query.tool_type
        if query.action_type:
            filter_query["action_type"] = query.action_type
        if status is not None:
            filter_query["status"] = status.value
        invocations = await self._find_many(filter_query)
        if not query.project_id:
            return _sorted_invocations(invocations)
        matched: list[ToolInvocation] = []
        for invocation in invocations:
            if invocation.action_request_id is None:
                continue
            request = await self._action_requests.get(invocation.action_request_id)
            if request is not None and request.project.project_id == query.project_id:
                matched.append(invocation)
        return _sorted_invocations(matched)


class _MongoWorkflowEventStore(_MongoRecordRepository[WorkflowEvent]):
    def __init__(self, provider: MongoPersistenceProvider) -> None:
        super().__init__(provider, "workflow_events")

    async def append(self, event: WorkflowEvent) -> None:
        await self._insert(event)

    async def get(self, event_id: str) -> WorkflowEvent | None:
        return await self._get(event_id)

    async def list_for_subject(self, subject: EventSubject) -> Sequence[WorkflowEvent]:
        return _sorted_events(
            await self._find_many(
                {
                    "subject.subject_type": subject.subject_type,
                    "subject.subject_id": subject.subject_id,
                }
            )
        )

    async def list_for_correlation(self, correlation_id: str) -> Sequence[WorkflowEvent]:
        return _sorted_events(await self._find_many({"correlation_id": correlation_id}))

    async def list_recent(self, *, limit: int) -> Sequence[WorkflowEvent]:
        if limit <= 0:
            return ()
        return _sorted_events(await self._find_many())[-limit:]


def _index_model(index_spec: MongoIndexSpec) -> IndexModel:
    kwargs: dict[str, Any] = {
        "name": index_spec.name,
        "unique": index_spec.unique,
    }
    if index_spec.partial_filter_expression is not None:
        kwargs["partialFilterExpression"] = dict(index_spec.partial_filter_expression)
    return IndexModel(list(index_spec.keys), **kwargs)


def _document_for_model(model: BaseModel, id_field: str) -> Document:
    data = cast(Document, _to_bson_value(model.model_dump(mode="python")))
    data["_id"] = data[id_field]
    return data


def _model_from_document[T: BaseModel](
    model_type: type[T],
    document: Mapping[str, Any],
) -> T:
    data = dict(document)
    data.pop("_id", None)
    return model_type.model_validate(_ensure_utc_datetimes(data))


def _to_bson_value(value: object) -> object:
    if isinstance(value, datetime):
        return value.astimezone(UTC)
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, Mapping):
        return {str(key): _to_bson_value(nested) for key, nested in value.items()}
    if isinstance(value, tuple | list):
        return [_to_bson_value(nested) for nested in value]
    return value


def _ensure_utc_datetimes(value: object) -> object:
    if isinstance(value, datetime):
        if value.tzinfo is None or value.utcoffset() is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)
    if isinstance(value, Mapping):
        return {str(key): _ensure_utc_datetimes(nested) for key, nested in value.items()}
    if isinstance(value, list):
        return [_ensure_utc_datetimes(nested) for nested in value]
    return value


def _lease_worker_filter(query: LeaseLookupQuery) -> dict[str, Any]:
    if query.worker_id:
        return {"state.lease.worker_id": query.worker_id}
    return {"state.lease": {"$ne": None}}


def _tool_action_filter(query: ToolActionQuery) -> dict[str, Any]:
    filter_query: dict[str, Any] = {}
    if query.tool_type:
        filter_query["tool_type"] = query.tool_type
    if query.action_type:
        filter_query["action_type"] = query.action_type
    if query.project_id:
        filter_query["project.project_id"] = query.project_id
    return filter_query


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


def _sorted_by_id[T](items: Iterable[T], key: Callable[[T], str]) -> tuple[T, ...]:
    return tuple(sorted(items, key=key))


def _sorted_work_items(items: Iterable[WorkItem]) -> tuple[WorkItem, ...]:
    return tuple(sorted(items, key=lambda item: (item.created_at, item.work_item_id)))


def _sorted_state_records(items: Iterable[WorkflowStateRecord]) -> tuple[WorkflowStateRecord, ...]:
    return tuple(sorted(items, key=lambda item: (item.updated_at, item.work_item_id)))


def _sorted_gates(items: Iterable[ApprovalGate]) -> tuple[ApprovalGate, ...]:
    return tuple(sorted(items, key=lambda item: (item.created_at, item.gate_id)))


def _sorted_invocations(items: Iterable[ToolInvocation]) -> tuple[ToolInvocation, ...]:
    return tuple(sorted(items, key=lambda item: (item.happened_at, item.tool_invocation_id)))


def _sorted_events(items: Iterable[WorkflowEvent]) -> tuple[WorkflowEvent, ...]:
    return tuple(sorted(items, key=lambda item: (item.happened_at, item.event_id)))
