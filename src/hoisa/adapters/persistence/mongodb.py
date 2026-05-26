"""MongoDB persistence adapter for Hoisa repositories and events."""

from collections.abc import AsyncIterator, Awaitable, Callable, Mapping, Sequence
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
from hoisa.domain.models import BsonObjectId, CollectionRoot
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
    RecordNotFoundError,
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
Hint = str | Sequence[SortKey]
ASCENDING = 1
DESCENDING = -1


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
class MongoCollectionSpec[T: BaseModel]:
    """Explicit collection mapping for a persisted Hoisa record type."""

    collection_name: str
    model_type: type[T]
    duplicate_label: str
    indexes: tuple[MongoIndexSpec, ...] = ()


MONGO_COLLECTION_SPECS: tuple[MongoCollectionSpec[Any], ...] = (
    MongoCollectionSpec(
        collection_name="projects",
        model_type=Project,
        duplicate_label="project",
    ),
    MongoCollectionSpec(
        collection_name="target_repos",
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
                keys=(("project.id", ASCENDING), ("_id", ASCENDING)),
            ),
        ),
    ),
    MongoCollectionSpec(
        collection_name="source_connections",
        model_type=SourceConnection,
        duplicate_label="source connection",
        indexes=(
            MongoIndexSpec(
                name="project_target_source_status_lookup",
                keys=(
                    ("project.id", ASCENDING),
                    ("target_repo.id", ASCENDING),
                    ("source_system", ASCENDING),
                    ("status", ASCENDING),
                ),
            ),
        ),
    ),
    MongoCollectionSpec(
        collection_name="source_observations",
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
                keys=(("target_repo.project.id", ASCENDING), ("target_repo.id", ASCENDING)),
            ),
            MongoIndexSpec(
                name="workflow_stage_status_risk_created_lookup",
                keys=(
                    ("workflow_stage", ASCENDING),
                    ("status", ASCENDING),
                    ("risk", ASCENDING),
                    ("created_at", ASCENDING),
                    ("_id", ASCENDING),
                ),
            ),
        ),
    ),
    MongoCollectionSpec(
        collection_name="workflow_states",
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
                keys=(("state.lease.worker_id", ASCENDING), ("state.lease.expires_at", ASCENDING)),
            ),
            MongoIndexSpec(
                name="updated_work_item_lookup",
                keys=(("updated_at", ASCENDING), ("work_item_id", ASCENDING)),
            ),
        ),
    ),
    MongoCollectionSpec(
        collection_name="approval_gates",
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
                keys=(("gate_status", ASCENDING), ("created_at", ASCENDING), ("_id", ASCENDING)),
            ),
        ),
    ),
    MongoCollectionSpec(
        collection_name="agent_runs",
        model_type=AgentRun,
        duplicate_label="agent run",
        indexes=(
            MongoIndexSpec(
                name="work_item_stage_started_lookup",
                keys=(
                    ("work_item_id", ASCENDING),
                    ("workflow_stage", ASCENDING),
                    ("started_at", ASCENDING),
                    ("_id", ASCENDING),
                ),
            ),
        ),
    ),
    MongoCollectionSpec(
        collection_name="evidence_bundles",
        model_type=EvidenceBundle,
        duplicate_label="evidence bundle",
        indexes=(
            MongoIndexSpec(
                name="subject_lookup",
                keys=(("subject_type", ASCENDING), ("subject_id", ASCENDING), ("_id", ASCENDING)),
            ),
        ),
    ),
    MongoCollectionSpec(
        collection_name="tool_connections",
        model_type=ToolConnection,
        duplicate_label="tool connection",
        indexes=(
            MongoIndexSpec(
                name="project_tool_status_lookup",
                keys=(("project.id", ASCENDING), ("tool_type", ASCENDING), ("status", ASCENDING)),
            ),
        ),
    ),
    MongoCollectionSpec(
        collection_name="tool_policies",
        model_type=ToolPolicy,
        duplicate_label="tool policy",
        indexes=(
            MongoIndexSpec(
                name="project_tool_action_unique",
                keys=(
                    ("project.id", ASCENDING),
                    ("tool_type", ASCENDING),
                    ("action_type", ASCENDING),
                ),
                unique=True,
            ),
            MongoIndexSpec(
                name="project_tool_action_lookup",
                keys=(
                    ("project.id", ASCENDING),
                    ("tool_type", ASCENDING),
                    ("action_type", ASCENDING),
                ),
            ),
        ),
    ),
    MongoCollectionSpec(
        collection_name="action_requests",
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
                    ("project.id", ASCENDING),
                    ("tool_type", ASCENDING),
                    ("action_type", ASCENDING),
                ),
            ),
        ),
    ),
    MongoCollectionSpec(
        collection_name="tool_invocations",
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
        model_type=WorkflowEvent,
        duplicate_label="Workflow event",
        indexes=(
            MongoIndexSpec(
                name="subject_happened_lookup",
                keys=(
                    ("subject.subject_type", ASCENDING),
                    ("subject.subject_id", ASCENDING),
                    ("happened_at", ASCENDING),
                    ("_id", ASCENDING),
                ),
            ),
            MongoIndexSpec(
                name="correlation_happened_lookup",
                keys=(
                    ("correlation_id", ASCENDING),
                    ("happened_at", ASCENDING),
                    ("_id", ASCENDING),
                ),
            ),
            MongoIndexSpec(
                name="happened_lookup",
                keys=(("happened_at", ASCENDING), ("_id", ASCENDING)),
            ),
        ),
    ),
)


class MongoAdapter:
    """Type-directed MongoDB mapper for Hoisa domain records."""

    def __init__(
        self,
        client: AsyncMongoClient[Document],
        *,
        database_name: str,
        collection_specs: Sequence[MongoCollectionSpec[Any]] = MONGO_COLLECTION_SPECS,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        codec_options: CodecOptions[Document] = CodecOptions(tz_aware=True, tzinfo=UTC)
        self._client = client
        self._database = client.get_database(database_name, codec_options=codec_options)
        self._clock = clock or (lambda: datetime.now(UTC))
        self._specs_by_model = {spec.model_type: spec for spec in collection_specs}

    async def find_one[T: BaseModel](
        self,
        model_type: type[T],
        *,
        id: BsonObjectId | None = None,
        query: Filter | None = None,
        sort: Sequence[SortKey] | None = None,
        hint: Hint | None = None,
    ) -> T | None:
        spec = self._spec_for(model_type)
        try:
            document = await self._collection(spec).find_one(
                self._query(id=id, query=query),
                sort=list(sort) if sort is not None else None,
                hint=hint,
            )
        except PyMongoError as exc:
            raise PersistenceError(f"Failed to read {spec.duplicate_label}.") from exc
        if document is None:
            return None
        return self._entity_from_document(model_type, cast(Mapping[str, Any], document))

    async def find[T: BaseModel](
        self,
        model_type: type[T],
        *,
        query: Filter | None = None,
        sort: Sequence[SortKey] | None = None,
        hint: Hint | None = None,
        limit: int | None = None,
    ) -> AsyncIterator[T]:
        spec = self._spec_for(model_type)
        try:
            cursor = self._collection(spec).find(
                self._query(query=query),
                sort=list(sort) if sort is not None else None,
                hint=hint,
            )
            if limit is not None:
                cursor = cursor.limit(limit)
            async for document in cursor:
                yield self._entity_from_document(model_type, cast(Mapping[str, Any], document))
        except PyMongoError as exc:
            raise PersistenceError(f"Failed to list {spec.duplicate_label}.") from exc

    async def find_many[T: BaseModel](
        self,
        model_type: type[T],
        *,
        query: Filter | None = None,
        sort: Sequence[SortKey] | None = None,
        hint: Hint | None = None,
        limit: int | None = None,
    ) -> tuple[T, ...]:
        return tuple(
            [
                entity
                async for entity in self.find(
                    model_type,
                    query=query,
                    sort=sort,
                    hint=hint,
                    limit=limit,
                )
            ]
        )

    async def insert_entity[T: BaseModel](self, entity: T) -> None:
        spec = self._spec_for(type(entity))
        try:
            await self._collection(spec).insert_one(self._document_for_entity(entity))
        except DuplicateKeyError as exc:
            raise DuplicateRecordError(f"{spec.duplicate_label} already exists.") from exc
        except PyMongoError as exc:
            raise PersistenceError(f"Failed to insert {spec.duplicate_label}.") from exc

    async def update_entity[T: BaseModel](self, entity: T) -> None:
        spec = self._spec_for(type(entity))
        document = self._document_for_entity(self._touch_updated_at(entity))
        try:
            result = await self._collection(spec).replace_one(
                {"_id": document["_id"]},
                document,
                upsert=False,
            )
        except DuplicateKeyError as exc:
            raise DuplicateRecordError(f"Duplicate {spec.duplicate_label}.") from exc
        except PyMongoError as exc:
            raise PersistenceError(f"Failed to update {spec.duplicate_label}.") from exc
        if result.matched_count == 0:
            raise RecordNotFoundError(f"{spec.duplicate_label} does not exist.")

    async def upsert_entity[T: BaseModel](self, entity: T) -> None:
        spec = self._spec_for(type(entity))
        document = self._document_for_entity(self._touch_updated_at(entity))
        try:
            await self._collection(spec).replace_one(
                {"_id": document["_id"]},
                document,
                upsert=True,
            )
        except DuplicateKeyError as exc:
            raise DuplicateRecordError(f"Duplicate {spec.duplicate_label}.") from exc
        except PyMongoError as exc:
            raise PersistenceError(f"Failed to save {spec.duplicate_label}.") from exc

    async def ensure_indexes(self) -> None:
        try:
            for spec in self._specs_by_model.values():
                models = [self._index_model(index) for index in spec.indexes]
                if models:
                    await self._collection(spec).create_indexes(models)
        except PyMongoError as exc:
            raise PersistenceError("Failed to ensure MongoDB persistence indexes.") from exc

    async def close(self) -> None:
        result = self._client.close()
        if isawaitable(result):
            await cast(Awaitable[None], result)

    def _spec_for[T: BaseModel](self, model_type: type[T]) -> MongoCollectionSpec[T]:
        try:
            return cast(MongoCollectionSpec[T], self._specs_by_model[model_type])
        except KeyError as exc:
            raise PersistenceError(f"No MongoDB collection registered for {model_type}.") from exc

    def _collection(self, spec: MongoCollectionSpec[Any]) -> Any:
        return self._database.get_collection(spec.collection_name)

    def _query(
        self,
        *,
        id: BsonObjectId | None = None,
        query: Filter | None = None,
    ) -> Document:
        filter_query = dict(query or {})
        if id is not None:
            filter_query["_id"] = id
        return cast(Document, self._to_bson_value(filter_query))

    def _document_for_entity(self, entity: BaseModel) -> Document:
        data = cast(Document, self._to_bson_value(entity.model_dump(mode="python")))
        document_id = data.pop("id")
        return {"_id": document_id, **data}

    def _entity_from_document[T: BaseModel](
        self,
        model_type: type[T],
        document: Mapping[str, Any],
    ) -> T:
        data = dict(document)
        data["id"] = data.pop("_id")
        return model_type.model_validate(self._ensure_utc_datetimes(data))

    def _touch_updated_at[T: BaseModel](self, entity: T) -> T:
        if isinstance(entity, CollectionRoot):
            return cast(T, entity.model_copy(update={"updated_at": self._clock()}))
        return entity

    def _index_model(self, index_spec: MongoIndexSpec) -> IndexModel:
        kwargs: dict[str, Any] = {
            "name": index_spec.name,
            "unique": index_spec.unique,
        }
        if index_spec.partial_filter_expression is not None:
            kwargs["partialFilterExpression"] = dict(index_spec.partial_filter_expression)
        return IndexModel(list(index_spec.keys), **kwargs)

    def _to_bson_value(self, value: object) -> object:
        if isinstance(value, datetime):
            return value.astimezone(UTC)
        if isinstance(value, Enum):
            return value.value
        if isinstance(value, Mapping):
            return {str(key): self._to_bson_value(nested) for key, nested in value.items()}
        if isinstance(value, tuple | list):
            return [self._to_bson_value(nested) for nested in value]
        return value

    def _ensure_utc_datetimes(self, value: object) -> object:
        if isinstance(value, datetime):
            if value.tzinfo is None or value.utcoffset() is None:
                return value.replace(tzinfo=UTC)
            return value.astimezone(UTC)
        if isinstance(value, Mapping):
            return {str(key): self._ensure_utc_datetimes(nested) for key, nested in value.items()}
        if isinstance(value, list):
            return [self._ensure_utc_datetimes(nested) for nested in value]
        return value


class MongoPersistenceProvider(PersistenceProvider):
    """MongoDB implementation of all persistence repositories."""

    def __init__(
        self,
        client: AsyncMongoClient[Document],
        *,
        database_name: str,
    ) -> None:
        self.adapter = MongoAdapter(client, database_name=database_name)
        self.database_name = database_name
        self._projects = MongoProjectRepository(self.adapter)
        self._target_repos = MongoTargetRepoRepository(self.adapter)
        self._source_connections = MongoSourceConnectionRepository(self.adapter)
        self._source_observations = MongoSourceObservationRepository(self.adapter)
        self._sync_cursors = MongoSyncCursorRepository(self.adapter)
        self._workflow_states = MongoWorkflowStateRepository(self.adapter)
        self._work_items = MongoWorkItemRepository(self.adapter, self._workflow_states)
        self._gates = MongoApprovalGateRepository(self.adapter, self._work_items)
        self._agent_runs = MongoAgentRunRepository(self.adapter)
        self._evidence_bundles = MongoEvidenceBundleRepository(self.adapter)
        self._tool_connections = MongoToolConnectionRepository(self.adapter)
        self._tool_policies = MongoToolPolicyRepository(self.adapter)
        self._action_requests = MongoActionRequestRepository(self.adapter)
        self._tool_invocations = MongoToolInvocationRepository(
            self.adapter,
            self._action_requests,
        )
        self._workflow_events = MongoWorkflowEventStore(self.adapter)

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

        await self.adapter.ensure_indexes()

    async def close(self) -> None:
        """Close the underlying MongoDB client."""

        await self.adapter.close()

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


class MongoProjectRepository:
    def __init__(self, adapter: MongoAdapter) -> None:
        self._adapter = adapter

    async def save(self, project: Project) -> None:
        await self._adapter.upsert_entity(project)

    async def get(self, project_id: BsonObjectId) -> Project | None:
        return await self._adapter.find_one(Project, id=project_id)

    async def list_all(self) -> Sequence[Project]:
        return await self._adapter.find_many(Project, sort=(("_id", ASCENDING),))


class MongoTargetRepoRepository:
    def __init__(self, adapter: MongoAdapter) -> None:
        self._adapter = adapter

    async def save(self, target_repo: TargetRepo) -> None:
        await self._adapter.upsert_entity(target_repo)

    async def get(self, target_repo_id: BsonObjectId) -> TargetRepo | None:
        return await self._adapter.find_one(TargetRepo, id=target_repo_id)

    async def get_by_provider(self, lookup: RepoLookup) -> TargetRepo | None:
        return await self._adapter.find_one(
            TargetRepo,
            query={
                "provider": lookup.provider,
                "owner": lookup.owner,
                "name": lookup.name,
            },
        )

    async def list_by_project(self, project_id: BsonObjectId) -> Sequence[TargetRepo]:
        return await self._adapter.find_many(
            TargetRepo,
            query={"project.id": project_id},
            sort=(("_id", ASCENDING),),
        )


class MongoSourceConnectionRepository:
    def __init__(self, adapter: MongoAdapter) -> None:
        self._adapter = adapter

    async def save(self, connection: SourceConnection) -> None:
        await self._adapter.upsert_entity(connection)

    async def get(self, source_connection_id: BsonObjectId) -> SourceConnection | None:
        return await self._adapter.find_one(SourceConnection, id=source_connection_id)

    async def list_by_project(self, project_id: BsonObjectId) -> Sequence[SourceConnection]:
        return await self._adapter.find_many(
            SourceConnection,
            query={"project.id": project_id},
            sort=(("_id", ASCENDING),),
        )


class MongoSourceObservationRepository:
    def __init__(self, adapter: MongoAdapter) -> None:
        self._adapter = adapter

    async def save(self, observation: SourceObservation) -> None:
        await self._adapter.upsert_entity(observation)

    async def get(self, observation_id: BsonObjectId) -> SourceObservation | None:
        return await self._adapter.find_one(SourceObservation, id=observation_id)

    async def find_by_source(self, query: SourceObservationQuery) -> Sequence[SourceObservation]:
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


class MongoSyncCursorRepository:
    def __init__(self, adapter: MongoAdapter) -> None:
        self._adapter = adapter

    async def save(self, cursor: SyncCursor) -> None:
        await self._adapter.upsert_entity(cursor)

    async def get(self, key: SyncCursorKey) -> SyncCursor | None:
        return await self._adapter.find_one(
            SyncCursor,
            query={
                "source_connection_id": key.source_connection_id,
                "cursor_name": key.cursor_name,
            },
        )

    async def list_by_source(self, source_connection_id: BsonObjectId) -> Sequence[SyncCursor]:
        return await self._adapter.find_many(
            SyncCursor,
            query={"source_connection_id": source_connection_id},
            sort=(("_id", ASCENDING),),
        )


class MongoWorkItemRepository:
    def __init__(
        self,
        adapter: MongoAdapter,
        workflow_states: WorkflowStateRepository,
    ) -> None:
        self._adapter = adapter
        self._workflow_states = workflow_states

    async def save(self, work_item: WorkItem) -> None:
        await self._adapter.upsert_entity(work_item)

    async def get(self, work_item_id: BsonObjectId) -> WorkItem | None:
        return await self._adapter.find_one(WorkItem, id=work_item_id)

    async def find_by_tracker_issue(self, *, provider: str, issue_number: int) -> WorkItem | None:
        return await self._adapter.find_one(
            WorkItem,
            query={
                "tracker_issue.provider": provider,
                "tracker_issue.issue_number": issue_number,
            },
        )

    async def find_runnable(self, query: RunnableWorkQuery) -> Sequence[WorkItem]:
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


class MongoWorkflowStateRepository:
    def __init__(self, adapter: MongoAdapter) -> None:
        self._adapter = adapter

    async def save(self, state_record: WorkflowStateRecord) -> None:
        await self._adapter.upsert_entity(
            state_record.model_copy(update={"id": state_record.work_item_id})
        )

    async def get(self, work_item_id: BsonObjectId) -> WorkflowStateRecord | None:
        return await self._adapter.find_one(WorkflowStateRecord, id=work_item_id)

    async def list_by_worker(self, query: LeaseLookupQuery) -> Sequence[WorkflowStateRecord]:
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

    def _lease_worker_filter(self, query: LeaseLookupQuery) -> dict[str, Any]:
        if query.worker_id:
            return {"state.lease.worker_id": query.worker_id}
        return {"state.lease": {"$ne": None}}


class MongoApprovalGateRepository:
    def __init__(
        self,
        adapter: MongoAdapter,
        work_items: WorkItemRepository,
    ) -> None:
        self._adapter = adapter
        self._work_items = work_items

    async def save(self, gate: ApprovalGate) -> None:
        await self._adapter.upsert_entity(gate)

    async def get(self, gate_id: BsonObjectId) -> ApprovalGate | None:
        return await self._adapter.find_one(ApprovalGate, id=gate_id)

    async def list_by_work_item(self, work_item_id: BsonObjectId) -> Sequence[ApprovalGate]:
        return await self._adapter.find_many(
            ApprovalGate,
            query={"work_item_id": work_item_id},
            sort=(("created_at", ASCENDING), ("_id", ASCENDING)),
        )

    async def list_waiting(self, query: WaitingGateQuery) -> Sequence[ApprovalGate]:
        filter_query: dict[str, Any] = {"gate_status": GateStatus.WAITING}
        if query.work_item_id is not None:
            filter_query["work_item_id"] = query.work_item_id
        gates = await self._adapter.find_many(
            ApprovalGate,
            query=filter_query,
            sort=(("created_at", ASCENDING), ("_id", ASCENDING)),
        )
        if query.tracker_issue_number is None:
            return gates
        matched: list[ApprovalGate] = []
        for gate in gates:
            work_item = await self._work_items.get(gate.work_item_id)
            if (
                work_item is not None
                and work_item.tracker_issue is not None
                and work_item.tracker_issue.issue_number == query.tracker_issue_number
            ):
                matched.append(gate)
        return tuple(matched)


class MongoAgentRunRepository:
    def __init__(self, adapter: MongoAdapter) -> None:
        self._adapter = adapter

    async def save(self, run: AgentRun) -> None:
        await self._adapter.upsert_entity(run)

    async def get(self, run_id: BsonObjectId) -> AgentRun | None:
        return await self._adapter.find_one(AgentRun, id=run_id)

    async def list_by_work_item(self, work_item_id: BsonObjectId) -> Sequence[AgentRun]:
        return await self._adapter.find_many(
            AgentRun,
            query={"work_item_id": work_item_id},
            sort=(("started_at", ASCENDING), ("_id", ASCENDING)),
        )


class MongoEvidenceBundleRepository:
    def __init__(self, adapter: MongoAdapter) -> None:
        self._adapter = adapter

    async def save(self, bundle: EvidenceBundle) -> None:
        await self._adapter.upsert_entity(bundle)

    async def get(self, bundle_id: BsonObjectId) -> EvidenceBundle | None:
        return await self._adapter.find_one(EvidenceBundle, id=bundle_id)

    async def list_by_subject(
        self, *, subject_type: str, subject_id: BsonObjectId
    ) -> Sequence[EvidenceBundle]:
        return await self._adapter.find_many(
            EvidenceBundle,
            query={"subject_type": subject_type, "subject_id": subject_id},
            sort=(("_id", ASCENDING),),
        )


class MongoToolConnectionRepository:
    def __init__(self, adapter: MongoAdapter) -> None:
        self._adapter = adapter

    async def save(self, connection: ToolConnection) -> None:
        await self._adapter.upsert_entity(connection)

    async def get(self, tool_connection_id: BsonObjectId) -> ToolConnection | None:
        return await self._adapter.find_one(ToolConnection, id=tool_connection_id)

    async def list_by_project(self, project_id: BsonObjectId) -> Sequence[ToolConnection]:
        return await self._adapter.find_many(
            ToolConnection,
            query={"project.id": project_id},
            sort=(("_id", ASCENDING),),
        )


class MongoToolPolicyRepository:
    def __init__(self, adapter: MongoAdapter) -> None:
        self._adapter = adapter

    async def save(self, policy: ToolPolicy) -> None:
        await self._adapter.upsert_entity(policy)

    async def get(self, tool_policy_id: BsonObjectId) -> ToolPolicy | None:
        return await self._adapter.find_one(ToolPolicy, id=tool_policy_id)

    async def find_for_action(self, query: ToolActionQuery) -> Sequence[ToolPolicy]:
        return await self._adapter.find_many(
            ToolPolicy,
            query=self._tool_action_filter(query),
            sort=(("_id", ASCENDING),),
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


class MongoActionRequestRepository:
    def __init__(self, adapter: MongoAdapter) -> None:
        self._adapter = adapter

    async def save(self, request: ActionRequest) -> None:
        await self._adapter.upsert_entity(request)

    async def get(self, action_request_id: BsonObjectId) -> ActionRequest | None:
        return await self._adapter.find_one(ActionRequest, id=action_request_id)

    async def list_by_status(self, status: ActionRequestStatus) -> Sequence[ActionRequest]:
        return await self._adapter.find_many(
            ActionRequest,
            query={"status": status},
            sort=(("created_at", ASCENDING), ("_id", ASCENDING)),
        )

    async def list_for_gate(self, gate_id: BsonObjectId) -> Sequence[ActionRequest]:
        return await self._adapter.find_many(
            ActionRequest,
            query={"required_gate_id": gate_id},
            sort=(("created_at", ASCENDING), ("_id", ASCENDING)),
        )


class MongoToolInvocationRepository:
    def __init__(
        self,
        adapter: MongoAdapter,
        action_requests: ActionRequestRepository,
    ) -> None:
        self._adapter = adapter
        self._action_requests = action_requests

    async def save(self, invocation: ToolInvocation) -> None:
        await self._adapter.upsert_entity(invocation)

    async def get(self, tool_invocation_id: BsonObjectId) -> ToolInvocation | None:
        return await self._adapter.find_one(ToolInvocation, id=tool_invocation_id)

    async def list_for_action_request(
        self,
        action_request_id: BsonObjectId,
    ) -> Sequence[ToolInvocation]:
        return await self._adapter.find_many(
            ToolInvocation,
            query={"action_request_id": action_request_id},
            sort=(("happened_at", ASCENDING), ("_id", ASCENDING)),
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
            filter_query["status"] = status
        invocations = await self._adapter.find_many(
            ToolInvocation,
            query=filter_query,
            sort=(("happened_at", ASCENDING), ("_id", ASCENDING)),
        )
        if query.project_id is None:
            return invocations
        matched: list[ToolInvocation] = []
        for invocation in invocations:
            if invocation.action_request_id is None:
                continue
            request = await self._action_requests.get(invocation.action_request_id)
            if request is not None and request.project.id == query.project_id:
                matched.append(invocation)
        return tuple(matched)


class MongoWorkflowEventStore:
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
