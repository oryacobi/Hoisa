"""Generic persistence contracts and workflow query inputs."""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol

from antonic import AntDoc

from hoisa.domain.events import EventSubject, WorkflowEvent
from hoisa.domain.gates import ApprovalGate
from hoisa.domain.models import RecordId
from hoisa.domain.target_repos import RepositoryProvider, TargetRepo
from hoisa.domain.tool_control import ToolInvocation, ToolInvocationStatus, ToolPolicy
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
    project_id: RecordId | None = None
    target_repo_id: RecordId | None = None
    now: datetime | None = None
    include_blocked: bool = False


@dataclass(frozen=True, slots=True)
class WaitingGateQuery:
    """Query for gates waiting on a human decision."""

    work_item_id: RecordId | None = None
    tracker_issue_number: int | None = None


@dataclass(frozen=True, slots=True)
class LeaseLookupQuery:
    """Query for workflow leases by worker or time boundary."""

    worker_id: str = ""
    now: datetime | None = None


@dataclass(frozen=True, slots=True)
class SourceObservationQuery:
    """Query for source observations by external identity."""

    source_connection_id: RecordId
    external_id: str = ""
    content_hash_value: str = ""


@dataclass(frozen=True, slots=True)
class SyncCursorKey:
    """Stable key for a source sync cursor."""

    source_connection_id: RecordId
    cursor_name: str


@dataclass(frozen=True, slots=True)
class ToolActionQuery:
    """Query for tool-control records by action surface."""

    project_id: RecordId | None = None
    tool_type: str = ""
    action_type: str = ""


@dataclass(frozen=True, slots=True)
class EventQuery:
    """Query for append-only workflow events."""

    subject: EventSubject | None = None
    correlation_id: str = ""
    limit: int | None = None


class PersistenceStore(Protocol):
    """Antonic-style generic persistence surface used by Hoisa."""

    async def insert[T: AntDoc](self, ant_doc: T) -> T:
        """Insert a new document and return the stored version."""
        ...

    async def save[T: AntDoc](self, ant_doc: T) -> T:
        """Save an existing document and return the stored version."""
        ...

    async def get[T: AntDoc](
        self,
        doc_type: type[T],
        id: Any = None,
        filter: Mapping[str, Any] | None = None,
        *,
        sort: Any = None,
        **where: Any,
    ) -> T | None:
        """Return one document by ID or filter."""
        ...

    async def find[T: AntDoc](
        self,
        doc_type: type[T],
        filter: Mapping[str, Any] | None = None,
        *,
        sort: Any = None,
        limit: int | None = None,
        skip: int | None = None,
        **where: Any,
    ) -> list[T]:
        """Return documents for a filter."""
        ...

    async def append_event(self, event: WorkflowEvent) -> WorkflowEvent:
        """Append a workflow event."""
        ...

    async def find_runnable_work(self, query: RunnableWorkQuery) -> Sequence[WorkItem]:
        """Return runnable work based on Hoisa-owned state."""
        ...

    async def list_waiting_gates(self, query: WaitingGateQuery) -> Sequence[ApprovalGate]:
        """Return gates waiting for a human decision."""
        ...

    async def list_active_leases(self, query: LeaseLookupQuery) -> Sequence[WorkflowStateRecord]:
        """Return workflow states with active leases at the query time."""
        ...

    async def list_expired_leases(self, query: LeaseLookupQuery) -> Sequence[WorkflowStateRecord]:
        """Return workflow states with expired leases at the query time."""
        ...

    async def list_tool_policies_for_action(self, query: ToolActionQuery) -> Sequence[ToolPolicy]:
        """Return policies that match a tool action query."""
        ...

    async def list_tool_invocations_by_action(
        self,
        query: ToolActionQuery,
        *,
        status: ToolInvocationStatus | None = None,
    ) -> Sequence[ToolInvocation]:
        """Return invocations by tool/action query."""
        ...

    async def list_events_for_subject(self, subject: EventSubject) -> Sequence[WorkflowEvent]:
        """Return events for a subject."""
        ...

    async def list_events_for_correlation(self, correlation_id: str) -> Sequence[WorkflowEvent]:
        """Return events for a correlation chain."""
        ...

    async def list_recent_events(self, *, limit: int) -> Sequence[WorkflowEvent]:
        """Return recent events in deterministic order."""
        ...


def repo_lookup_filter(lookup: RepoLookup) -> Mapping[str, Any]:
    """Return the generic filter for a repository provider identity."""

    return {"provider": lookup.provider, "owner": lookup.owner, "name": lookup.name}


def source_observation_filter(query: SourceObservationQuery) -> Mapping[str, Any]:
    """Return the generic filter for a source observation query."""

    filters: dict[str, Any] = {"source_connection_id": query.source_connection_id}
    if query.external_id:
        filters["external_id"] = query.external_id
    if query.content_hash_value:
        filters["content_hash.value"] = query.content_hash_value
    return filters


def sync_cursor_filter(key: SyncCursorKey) -> Mapping[str, Any]:
    """Return the generic filter for a sync cursor key."""

    return {"source_connection_id": key.source_connection_id, "cursor_name": key.cursor_name}


def target_repo_filter(target_repo: TargetRepo) -> Mapping[str, Any]:
    """Return the generic filter for a target repository identity."""

    return {
        "provider": target_repo.provider,
        "owner": target_repo.owner,
        "name": target_repo.name,
    }
