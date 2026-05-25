"""Persistence ports for Hoisa current-state repositories and event history."""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from hoisa.domain.events import EventSubject, WorkflowEvent
from hoisa.domain.evidence import EvidenceBundle
from hoisa.domain.gates import ApprovalGate
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
    project_id: str = ""
    target_repo_id: str = ""
    now: datetime | None = None
    include_blocked: bool = False


@dataclass(frozen=True, slots=True)
class WaitingGateQuery:
    """Query for gates waiting on a human decision."""

    work_item_id: str = ""
    tracker_issue_number: int | None = None


@dataclass(frozen=True, slots=True)
class LeaseLookupQuery:
    """Query for workflow leases by worker or time boundary."""

    worker_id: str = ""
    now: datetime | None = None


@dataclass(frozen=True, slots=True)
class SourceObservationQuery:
    """Query for source observations by external identity."""

    source_connection_id: str
    external_id: str = ""
    content_hash_value: str = ""


@dataclass(frozen=True, slots=True)
class SyncCursorKey:
    """Stable key for a source sync cursor."""

    source_connection_id: str
    cursor_name: str


@dataclass(frozen=True, slots=True)
class ToolActionQuery:
    """Query for tool-control records by action surface."""

    project_id: str = ""
    tool_type: str = ""
    action_type: str = ""


@dataclass(frozen=True, slots=True)
class EventQuery:
    """Query for append-only workflow events."""

    subject: EventSubject | None = None
    correlation_id: str = ""
    limit: int | None = None


class ProjectRepository(Protocol):
    """Repository for Hoisa project records."""

    async def save(self, project: Project) -> None:
        """Save a project snapshot."""
        ...

    async def get(self, project_id: str) -> Project | None:
        """Return a project by stable ID."""
        ...

    async def list_all(self) -> Sequence[Project]:
        """Return all projects in deterministic order."""
        ...


class TargetRepoRepository(Protocol):
    """Repository for target repository records."""

    async def save(self, target_repo: TargetRepo) -> None:
        """Save a target repository snapshot."""
        ...

    async def get(self, target_repo_id: str) -> TargetRepo | None:
        """Return a target repository by stable ID."""
        ...

    async def get_by_provider(self, lookup: RepoLookup) -> TargetRepo | None:
        """Return a target repository by provider, owner, and name."""
        ...

    async def list_by_project(self, project_id: str) -> Sequence[TargetRepo]:
        """Return repositories for a Hoisa project."""
        ...


class SourceConnectionRepository(Protocol):
    """Repository for external source connections."""

    async def save(self, connection: SourceConnection) -> None:
        """Save a source connection snapshot."""
        ...

    async def get(self, source_connection_id: str) -> SourceConnection | None:
        """Return a source connection by stable ID."""
        ...

    async def list_by_project(self, project_id: str) -> Sequence[SourceConnection]:
        """Return source connections for a project."""
        ...


class SourceObservationRepository(Protocol):
    """Repository for public-safe source observations."""

    async def save(self, observation: SourceObservation) -> None:
        """Save a source observation snapshot."""
        ...

    async def get(self, observation_id: str) -> SourceObservation | None:
        """Return a source observation by stable ID."""
        ...

    async def find_by_source(self, query: SourceObservationQuery) -> Sequence[SourceObservation]:
        """Return observations for a source query."""
        ...


class SyncCursorRepository(Protocol):
    """Repository for source sync cursors."""

    async def save(self, cursor: SyncCursor) -> None:
        """Save a cursor snapshot."""
        ...

    async def get(self, key: SyncCursorKey) -> SyncCursor | None:
        """Return a cursor by source connection and cursor name."""
        ...

    async def list_by_source(self, source_connection_id: str) -> Sequence[SyncCursor]:
        """Return all cursors for a source connection."""
        ...


class WorkItemRepository(Protocol):
    """Repository for canonical Hoisa work items."""

    async def save(self, work_item: WorkItem) -> None:
        """Save a work item snapshot."""
        ...

    async def get(self, work_item_id: str) -> WorkItem | None:
        """Return a work item by stable ID."""
        ...

    async def find_by_tracker_issue(self, *, provider: str, issue_number: int) -> WorkItem | None:
        """Return a work item by tracker issue identity."""
        ...

    async def find_runnable(self, query: RunnableWorkQuery) -> Sequence[WorkItem]:
        """Return runnable work based on Hoisa-owned state."""
        ...


class WorkflowStateRepository(Protocol):
    """Repository for workflow lifecycle and lease state."""

    async def save(self, state_record: WorkflowStateRecord) -> None:
        """Save a workflow state snapshot."""
        ...

    async def get(self, work_item_id: str) -> WorkflowStateRecord | None:
        """Return workflow state by work item."""
        ...

    async def list_by_worker(self, query: LeaseLookupQuery) -> Sequence[WorkflowStateRecord]:
        """Return workflow states leased by a worker."""
        ...

    async def list_active_leases(self, query: LeaseLookupQuery) -> Sequence[WorkflowStateRecord]:
        """Return workflow states with active leases at the query time."""
        ...

    async def list_expired_leases(self, query: LeaseLookupQuery) -> Sequence[WorkflowStateRecord]:
        """Return workflow states with expired leases at the query time."""
        ...


class ApprovalGateRepository(Protocol):
    """Repository for approval gates."""

    async def save(self, gate: ApprovalGate) -> None:
        """Save an approval gate snapshot."""
        ...

    async def get(self, gate_id: str) -> ApprovalGate | None:
        """Return a gate by stable ID."""
        ...

    async def list_by_work_item(self, work_item_id: str) -> Sequence[ApprovalGate]:
        """Return gates attached to a work item."""
        ...

    async def list_waiting(self, query: WaitingGateQuery) -> Sequence[ApprovalGate]:
        """Return gates waiting for a human decision."""
        ...


class AgentRunRepository(Protocol):
    """Repository for agent run summaries."""

    async def save(self, run: AgentRun) -> None:
        """Save an agent run snapshot."""
        ...

    async def get(self, run_id: str) -> AgentRun | None:
        """Return an agent run by stable ID."""
        ...

    async def list_by_work_item(self, work_item_id: str) -> Sequence[AgentRun]:
        """Return agent runs for a work item."""
        ...


class EvidenceBundleRepository(Protocol):
    """Repository for evidence bundles."""

    async def save(self, bundle: EvidenceBundle) -> None:
        """Save an evidence bundle snapshot."""
        ...

    async def get(self, bundle_id: str) -> EvidenceBundle | None:
        """Return an evidence bundle by stable ID."""
        ...

    async def list_by_subject(
        self, *, subject_type: str, subject_id: str
    ) -> Sequence[EvidenceBundle]:
        """Return evidence bundles for a subject."""
        ...


class ToolConnectionRepository(Protocol):
    """Repository for configured tool connections."""

    async def save(self, connection: ToolConnection) -> None:
        """Save a tool connection snapshot."""
        ...

    async def get(self, tool_connection_id: str) -> ToolConnection | None:
        """Return a tool connection by stable ID."""
        ...

    async def list_by_project(self, project_id: str) -> Sequence[ToolConnection]:
        """Return tool connections for a project."""
        ...


class ToolPolicyRepository(Protocol):
    """Repository for tool policies."""

    async def save(self, policy: ToolPolicy) -> None:
        """Save a tool policy snapshot."""
        ...

    async def get(self, tool_policy_id: str) -> ToolPolicy | None:
        """Return a tool policy by stable ID."""
        ...

    async def find_for_action(self, query: ToolActionQuery) -> Sequence[ToolPolicy]:
        """Return policies that match a tool action query."""
        ...


class ActionRequestRepository(Protocol):
    """Repository for external action requests."""

    async def save(self, request: ActionRequest) -> None:
        """Save an action request snapshot."""
        ...

    async def get(self, action_request_id: str) -> ActionRequest | None:
        """Return an action request by stable ID."""
        ...

    async def list_by_status(self, status: ActionRequestStatus) -> Sequence[ActionRequest]:
        """Return action requests by status."""
        ...

    async def list_for_gate(self, gate_id: str) -> Sequence[ActionRequest]:
        """Return action requests linked to a required gate."""
        ...


class ToolInvocationRepository(Protocol):
    """Repository for audited tool invocation attempts."""

    async def save(self, invocation: ToolInvocation) -> None:
        """Save a tool invocation snapshot."""
        ...

    async def get(self, tool_invocation_id: str) -> ToolInvocation | None:
        """Return a tool invocation by stable ID."""
        ...

    async def list_for_action_request(self, action_request_id: str) -> Sequence[ToolInvocation]:
        """Return invocations for an action request."""
        ...

    async def list_by_tool_action(
        self,
        query: ToolActionQuery,
        *,
        status: ToolInvocationStatus | None = None,
    ) -> Sequence[ToolInvocation]:
        """Return invocations by tool/action query."""
        ...


class WorkflowEventStore(Protocol):
    """Append-only workflow event store."""

    async def append(self, event: WorkflowEvent) -> None:
        """Append a workflow event."""
        ...

    async def get(self, event_id: str) -> WorkflowEvent | None:
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
    """Provider exposing typed persistence repositories."""

    @property
    def projects(self) -> ProjectRepository:
        """Return the project repository."""
        ...

    @property
    def target_repos(self) -> TargetRepoRepository:
        """Return the target repository repository."""
        ...

    @property
    def source_connections(self) -> SourceConnectionRepository:
        """Return the source connection repository."""
        ...

    @property
    def source_observations(self) -> SourceObservationRepository:
        """Return the source observation repository."""
        ...

    @property
    def sync_cursors(self) -> SyncCursorRepository:
        """Return the sync cursor repository."""
        ...

    @property
    def work_items(self) -> WorkItemRepository:
        """Return the work item repository."""
        ...

    @property
    def workflow_states(self) -> WorkflowStateRepository:
        """Return the workflow state repository."""
        ...

    @property
    def gates(self) -> ApprovalGateRepository:
        """Return the approval gate repository."""
        ...

    @property
    def agent_runs(self) -> AgentRunRepository:
        """Return the agent run repository."""
        ...

    @property
    def evidence_bundles(self) -> EvidenceBundleRepository:
        """Return the evidence bundle repository."""
        ...

    @property
    def tool_connections(self) -> ToolConnectionRepository:
        """Return the tool connection repository."""
        ...

    @property
    def tool_policies(self) -> ToolPolicyRepository:
        """Return the tool policy repository."""
        ...

    @property
    def action_requests(self) -> ActionRequestRepository:
        """Return the action request repository."""
        ...

    @property
    def tool_invocations(self) -> ToolInvocationRepository:
        """Return the tool invocation repository."""
        ...

    @property
    def workflow_events(self) -> WorkflowEventStore:
        """Return the workflow event store."""
        ...
