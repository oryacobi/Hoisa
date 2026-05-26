"""Persistence ports for Hoisa durable workflow state."""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from hoisa.domain.events import EventSubject, WorkflowEvent
from hoisa.domain.evidence import EvidenceBundle
from hoisa.domain.gates import ApprovalGate
from hoisa.domain.models import BsonObjectId
from hoisa.domain.runs import AgentRun
from hoisa.domain.sources import SourceConnection, SourceObservation, SyncCursor
from hoisa.domain.target_repos import Project, RepositoryProvider, TargetRepo
from hoisa.domain.tool_control import (
    ActionRequest,
    ActionRequestStatus,
    ToolConnection,
    ToolInvocation,
    ToolInvocationStatus,
    ToolPolicy,
)
from hoisa.domain.work_items import WorkItem
from hoisa.domain.workflow_state import (
    QueueStatus,
    RiskLevel,
    WorkflowStage,
    WorkflowStateRecord,
)


class PersistenceError(RuntimeError):
    """Base class for adapter-neutral persistence failures."""


class DuplicateRecordError(PersistenceError):
    """Raised when a stable identity or unique key collides."""


class RecordNotFoundError(PersistenceError):
    """Raised when an operation requires an existing record."""


class PersistenceConflictError(PersistenceError):
    """Raised when a persistence operation would violate current state."""


@dataclass(frozen=True, slots=True)
class RepoLookup:
    """Provider-level repository lookup without adapter collection names."""

    provider: RepositoryProvider
    owner: str
    name: str


@dataclass(frozen=True, slots=True)
class RunnableWorkQuery:
    """Query for work Hoisa can select from canonical current-state records."""

    workflow_stage: WorkflowStage
    status: QueueStatus = QueueStatus.TODO
    risk: RiskLevel | None = None
    project_id: BsonObjectId | None = None
    target_repo_id: BsonObjectId | None = None
    now: datetime | None = None
    include_blocked: bool = False


@dataclass(frozen=True, slots=True)
class WaitingGateQuery:
    """Query for gates waiting on a human decision."""

    work_item_id: BsonObjectId | None = None
    tracker_issue_number: int | None = None


@dataclass(frozen=True, slots=True)
class LeaseLookupQuery:
    """Query for workflow leases by worker or time boundary."""

    worker_id: str = ""
    now: datetime | None = None


@dataclass(frozen=True, slots=True)
class SourceObservationQuery:
    """Query for source observations by external identity."""

    source_connection_id: BsonObjectId
    external_id: str = ""
    content_hash_value: str = ""


@dataclass(frozen=True, slots=True)
class SyncCursorKey:
    """Stable key for a source sync cursor."""

    source_connection_id: BsonObjectId
    cursor_name: str


@dataclass(frozen=True, slots=True)
class ToolActionQuery:
    """Query for tool-control records by action surface."""

    project_id: BsonObjectId | None = None
    tool_type: str = ""
    action_type: str = ""


@dataclass(frozen=True, slots=True)
class EventQuery:
    """Query for append-only workflow events."""

    subject: EventSubject | None = None
    correlation_id: str = ""
    limit: int | None = None


class CatalogGateway(Protocol):
    """Project and target repository persistence."""

    async def save_project(self, project: Project) -> None:
        """Save a project snapshot."""
        ...

    async def get_project(self, project_id: BsonObjectId) -> Project | None:
        """Return a project by stable ID."""
        ...

    async def list_projects(self) -> Sequence[Project]:
        """Return all projects in deterministic order."""
        ...

    async def save_target_repo(self, target_repo: TargetRepo) -> None:
        """Save a target repository snapshot."""
        ...

    async def get_target_repo(self, target_repo_id: BsonObjectId) -> TargetRepo | None:
        """Return a target repository by stable ID."""
        ...

    async def get_target_repo_by_provider(self, lookup: RepoLookup) -> TargetRepo | None:
        """Return a target repository by provider, owner, and name."""
        ...

    async def list_target_repos(self, project_id: BsonObjectId) -> Sequence[TargetRepo]:
        """Return repositories for a Hoisa project."""
        ...


class SourceGateway(Protocol):
    """External source connection, observation, and cursor persistence."""

    async def save_connection(self, connection: SourceConnection) -> None:
        """Save a source connection snapshot."""
        ...

    async def get_connection(self, source_connection_id: BsonObjectId) -> SourceConnection | None:
        """Return a source connection by stable ID."""
        ...

    async def list_connections(self, project_id: BsonObjectId) -> Sequence[SourceConnection]:
        """Return source connections for a project."""
        ...

    async def save_observation(self, observation: SourceObservation) -> None:
        """Save a source observation snapshot."""
        ...

    async def get_observation(self, observation_id: BsonObjectId) -> SourceObservation | None:
        """Return a source observation by stable ID."""
        ...

    async def find_observations(self, query: SourceObservationQuery) -> Sequence[SourceObservation]:
        """Return observations for a source query."""
        ...

    async def save_cursor(self, cursor: SyncCursor) -> None:
        """Save a cursor snapshot."""
        ...

    async def get_cursor(self, key: SyncCursorKey) -> SyncCursor | None:
        """Return a cursor by source connection and cursor name."""
        ...

    async def list_cursors(self, source_connection_id: BsonObjectId) -> Sequence[SyncCursor]:
        """Return all cursors for a source connection."""
        ...


class WorkflowGateway(Protocol):
    """Work item, workflow state, gate, and run persistence."""

    async def save_work_item(self, work_item: WorkItem) -> None:
        """Save a work item snapshot."""
        ...

    async def get_work_item(self, work_item_id: BsonObjectId) -> WorkItem | None:
        """Return a work item by stable ID."""
        ...

    async def find_work_item_by_tracker_issue(
        self, *, provider: str, issue_number: int
    ) -> WorkItem | None:
        """Return a work item by tracker issue identity."""
        ...

    async def find_runnable_work(self, query: RunnableWorkQuery) -> Sequence[WorkItem]:
        """Return runnable work based on Hoisa-owned state."""
        ...

    async def save_state(self, state_record: WorkflowStateRecord) -> None:
        """Save a workflow state snapshot."""
        ...

    async def get_state(self, work_item_id: BsonObjectId) -> WorkflowStateRecord | None:
        """Return workflow state by work item."""
        ...

    async def list_states_by_worker(self, query: LeaseLookupQuery) -> Sequence[WorkflowStateRecord]:
        """Return workflow states leased by a worker."""
        ...

    async def list_active_leases(self, query: LeaseLookupQuery) -> Sequence[WorkflowStateRecord]:
        """Return workflow states with active leases at the query time."""
        ...

    async def list_expired_leases(self, query: LeaseLookupQuery) -> Sequence[WorkflowStateRecord]:
        """Return workflow states with expired leases at the query time."""
        ...

    async def save_gate(self, gate: ApprovalGate) -> None:
        """Save an approval gate snapshot."""
        ...

    async def get_gate(self, gate_id: BsonObjectId) -> ApprovalGate | None:
        """Return a gate by stable ID."""
        ...

    async def list_gates(self, work_item_id: BsonObjectId) -> Sequence[ApprovalGate]:
        """Return gates attached to a work item."""
        ...

    async def list_waiting_gates(self, query: WaitingGateQuery) -> Sequence[ApprovalGate]:
        """Return gates waiting for a human decision."""
        ...

    async def save_agent_run(self, run: AgentRun) -> None:
        """Save an agent run snapshot."""
        ...

    async def get_agent_run(self, run_id: BsonObjectId) -> AgentRun | None:
        """Return an agent run by stable ID."""
        ...

    async def list_agent_runs(self, work_item_id: BsonObjectId) -> Sequence[AgentRun]:
        """Return agent runs for a work item."""
        ...


class EvidenceGateway(Protocol):
    """Evidence bundle persistence."""

    async def save_bundle(self, bundle: EvidenceBundle) -> None:
        """Save an evidence bundle snapshot."""
        ...

    async def get_bundle(self, bundle_id: BsonObjectId) -> EvidenceBundle | None:
        """Return an evidence bundle by stable ID."""
        ...

    async def list_bundles(
        self, *, subject_type: str, subject_id: BsonObjectId
    ) -> Sequence[EvidenceBundle]:
        """Return evidence bundles for a subject."""
        ...


class ToolGateway(Protocol):
    """Tool connection, policy, request, and invocation persistence."""

    async def save_connection(self, connection: ToolConnection) -> None:
        """Save a tool connection snapshot."""
        ...

    async def get_connection(self, tool_connection_id: BsonObjectId) -> ToolConnection | None:
        """Return a tool connection by stable ID."""
        ...

    async def list_connections(self, project_id: BsonObjectId) -> Sequence[ToolConnection]:
        """Return tool connections for a project."""
        ...

    async def save_policy(self, policy: ToolPolicy) -> None:
        """Save a tool policy snapshot."""
        ...

    async def get_policy(self, tool_policy_id: BsonObjectId) -> ToolPolicy | None:
        """Return a tool policy by stable ID."""
        ...

    async def find_policies(self, query: ToolActionQuery) -> Sequence[ToolPolicy]:
        """Return policies that match a tool action query."""
        ...

    async def save_action_request(self, request: ActionRequest) -> None:
        """Save an action request snapshot."""
        ...

    async def get_action_request(self, action_request_id: BsonObjectId) -> ActionRequest | None:
        """Return an action request by stable ID."""
        ...

    async def list_action_requests_by_status(
        self, status: ActionRequestStatus
    ) -> Sequence[ActionRequest]:
        """Return action requests by status."""
        ...

    async def list_action_requests_for_gate(self, gate_id: BsonObjectId) -> Sequence[ActionRequest]:
        """Return action requests linked to a required gate."""
        ...

    async def save_invocation(self, invocation: ToolInvocation) -> None:
        """Save a tool invocation snapshot."""
        ...

    async def get_invocation(self, tool_invocation_id: BsonObjectId) -> ToolInvocation | None:
        """Return a tool invocation by stable ID."""
        ...

    async def list_invocations_for_action_request(
        self, action_request_id: BsonObjectId
    ) -> Sequence[ToolInvocation]:
        """Return invocations for an action request."""
        ...

    async def list_invocations_by_tool_action(
        self,
        query: ToolActionQuery,
        *,
        status: ToolInvocationStatus | None = None,
    ) -> Sequence[ToolInvocation]:
        """Return invocations by tool/action query."""
        ...


class EventGateway(Protocol):
    """Append-only workflow event persistence."""

    async def append(self, event: WorkflowEvent) -> None:
        """Append a workflow event."""
        ...

    async def get(self, event_id: BsonObjectId) -> WorkflowEvent | None:
        """Return an event by stable ID."""
        ...

    async def list_for_subject(self, subject: EventSubject) -> Sequence[WorkflowEvent]:
        """Return events for a subject."""
        ...

    async def list_for_correlation(self, correlation_id: str) -> Sequence[WorkflowEvent]:
        """Return events for a correlation chain."""
        ...

    async def list_recent(self, *, limit: int) -> Sequence[WorkflowEvent]:
        """Return recent events in deterministic order."""
        ...


class PersistenceProvider(Protocol):
    """Provider exposing domain persistence gateways."""

    @property
    def catalog(self) -> CatalogGateway:
        """Return the project and target-repo gateway."""
        ...

    @property
    def sources(self) -> SourceGateway:
        """Return the source data gateway."""
        ...

    @property
    def workflow(self) -> WorkflowGateway:
        """Return the workflow state gateway."""
        ...

    @property
    def evidence(self) -> EvidenceGateway:
        """Return the evidence gateway."""
        ...

    @property
    def tools(self) -> ToolGateway:
        """Return the tool-control gateway."""
        ...

    @property
    def events(self) -> EventGateway:
        """Return the workflow event gateway."""
        ...
