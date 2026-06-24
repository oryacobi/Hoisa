"""Synchronize GitHub repository issues into Hoisa source and work records."""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
import hashlib
import json
from typing import Any

from antonic import AntDoc
from bson import ObjectId

from hoisa.app.services.github_connection_bootstrap import INITIAL_CURSOR_VALUE
from hoisa.app.services.issue_quality import evaluate_issue_quality
from hoisa.domain.actors import ActorRef, ActorType
from hoisa.domain.events import EventSubject, WorkflowEvent
from hoisa.domain.issue_quality import IssueQualityFinding, IssueQualityInput
from hoisa.domain.privacy import PublicSafetyClass, RedactionStatus
from hoisa.domain.provenance import ContentHash, SourceProvenance, SourceSystem
from hoisa.domain.sources import (
    ObservationScalar,
    SourceConnection,
    SourceConnectionResourceType,
    SourceConnectionStatus,
    SourceObservation,
    SyncCursor,
)
from hoisa.domain.work_items import TrackerIssueRef, WorkItem
from hoisa.domain.workflow_event_types import WorkflowEventType
from hoisa.domain.workflow_state import (
    Blocker,
    QueueStatus,
    ReviewRoute,
    RiskLevel,
    WorkflowStage,
    WorkflowState,
    WorkflowStateRecord,
    WorkItemType,
)
from hoisa.ports.persistence import (
    DuplicateRecordError,
    PersistenceStore,
    SourceObservationQuery,
    SyncCursorKey,
    source_observation_filter,
    sync_cursor_filter,
)
from hoisa.ports.source_sync import (
    GitHubIssueSnapshot,
    GitHubIssueSourceClient,
    GitHubIssueSyncRequest,
    SourceSyncError,
)

ISSUE_CURSOR_NAME = "issues"
GITHUB_ISSUE_PAYLOAD_SCHEMA = "github_issue_summary.v1"
GITHUB_ISSUE_SYNC_EVENT_SCHEMA = "github_issue_sync.v1"
GITHUB_TRACKER_PROVIDER = "github"


@dataclass(frozen=True, slots=True)
class GitHubIssueSyncResult:
    """Redactable result of a GitHub issue sync iteration."""

    applied: bool
    source_connections: int
    fetched_issues: int
    imported_issues: int
    skipped_pull_requests: int
    cursor_value: str
    created_counts: Mapping[str, int]
    updated_counts: Mapping[str, int]
    unchanged_counts: Mapping[str, int]

    def redacted_summary(self) -> dict[str, Any]:
        """Return safe operator output without repository identifiers."""

        return {
            "applied": self.applied,
            "source_connections": self.source_connections,
            "fetched_issues": self.fetched_issues,
            "imported_issues": self.imported_issues,
            "skipped_pull_requests": self.skipped_pull_requests,
            "cursor_value": self.cursor_value,
            "created": dict(self.created_counts),
            "updated": dict(self.updated_counts),
            "unchanged": dict(self.unchanged_counts),
        }


async def sync_github_repository_issues(
    *,
    client: GitHubIssueSourceClient,
    store: PersistenceStore,
    apply: bool = False,
    now: datetime | None = None,
) -> GitHubIssueSyncResult:
    """Fetch GitHub issues for active source connections and optionally persist them."""

    timestamp = (now or datetime.now(tz=UTC)).astimezone(UTC)
    writer = _GitHubIssueSyncWriter(client, store, apply=apply, now=timestamp)
    await writer.sync()
    return writer.result()


class _GitHubIssueSyncWriter:
    def __init__(
        self,
        client: GitHubIssueSourceClient,
        store: PersistenceStore,
        *,
        apply: bool,
        now: datetime,
    ) -> None:
        self.client = client
        self.store = store
        self.apply = apply
        self.now = now
        self.source_connections = 0
        self.fetched_issues = 0
        self.imported_issues = 0
        self.skipped_pull_requests = 0
        self.cursor_value = ""
        self._created: dict[str, int] = {}
        self._updated: dict[str, int] = {}
        self._unchanged: dict[str, int] = {}
        self._event_subject: EventSubject | None = None
        self._pending_cursor_updates: list[tuple[SyncCursor, str]] = []

    async def sync(self) -> None:
        sources = await self._active_sources()
        self.source_connections = len(sources)
        for source in sources:
            await self._sync_source(source)
        if self.apply and self._event_subject is not None:
            await self.store.append_event(self._event())
        for cursor, next_cursor in self._pending_cursor_updates:
            await self.store.save(
                cursor.model_copy(
                    update={
                        "cursor_value": next_cursor,
                        "source_provenance": self._provenance(
                            source_id=f"github-cursor:{ISSUE_CURSOR_NAME}"
                        ),
                    }
                )
            )
            self._count(self._updated, "sync_cursors")

    def result(self) -> GitHubIssueSyncResult:
        return GitHubIssueSyncResult(
            applied=self.apply,
            source_connections=self.source_connections,
            fetched_issues=self.fetched_issues,
            imported_issues=self.imported_issues,
            skipped_pull_requests=self.skipped_pull_requests,
            cursor_value=self.cursor_value,
            created_counts=self._created,
            updated_counts=self._updated,
            unchanged_counts=self._unchanged,
        )

    async def _active_sources(self) -> list[SourceConnection]:
        return await self.store.find(
            SourceConnection,
            filter={
                "source_system": SourceSystem.GITHUB,
                "status": SourceConnectionStatus.ACTIVE,
                "resource_type": SourceConnectionResourceType.GITHUB_REPOSITORY_ISSUES,
            },
            sort=[("created_at", 1), ("id", 1)],
        )

    async def _sync_source(self, source: SourceConnection) -> None:
        source_id = _source_id(source)
        if self._event_subject is None:
            self._event_subject = EventSubject(
                subject_type="source_connection",
                subject_id=source_id,
            )
        if source.target_repo is None:
            raise SourceSyncError("GitHub issue source is missing a target repository.")
        if not source.credential_ref:
            raise SourceSyncError("GitHub issue source is missing a credential reference.")

        cursor = await self.store.get(
            SyncCursor,
            filter=sync_cursor_filter(
                SyncCursorKey(source_connection_id=source_id, cursor_name=ISSUE_CURSOR_NAME)
            ),
        )
        if cursor is None:
            raise SourceSyncError("GitHub issue source is missing an issues sync cursor.")

        request = GitHubIssueSyncRequest(
            credential_ref=source.credential_ref,
            repo_owner=source.target_repo.owner,
            repo_name=source.target_repo.name,
            since=_cursor_since(cursor.cursor_value),
        )
        snapshots = tuple(self.client.list_repository_issues(request))
        self.fetched_issues += len(snapshots)
        issues = tuple(snapshot for snapshot in snapshots if not snapshot.is_pull_request)
        self.skipped_pull_requests += len(snapshots) - len(issues)
        self.imported_issues += len(issues)

        for issue in issues:
            await self._observe_issue(source, issue)
            await self._upsert_work_item(source, issue)

        next_cursor = _next_cursor_value(cursor.cursor_value, issues, self.now)
        self.cursor_value = next_cursor
        if self.apply and next_cursor != cursor.cursor_value:
            self._pending_cursor_updates.append((cursor, next_cursor))
        elif next_cursor == cursor.cursor_value:
            self._count(self._unchanged, "sync_cursors")

    async def _observe_issue(self, source: SourceConnection, issue: GitHubIssueSnapshot) -> None:
        observation = _source_observation(source, issue, self.now)
        existing = await self.store.get(
            SourceObservation,
            filter=source_observation_filter(
                SourceObservationQuery(
                    source_connection_id=_source_id(source),
                    external_id=observation.external_id,
                    content_hash_value=observation.content_hash.value,
                )
            ),
        )
        if existing is not None:
            self._count(self._unchanged, "source_observations")
            return
        if not self.apply:
            self._count(self._created, "source_observations")
            return
        try:
            await self.store.insert(observation)
        except DuplicateRecordError:
            self._count(self._unchanged, "source_observations")
            return
        self._count(self._created, "source_observations")

    async def _upsert_work_item(
        self,
        source: SourceConnection,
        issue: GitHubIssueSnapshot,
    ) -> None:
        if source.target_repo is None:
            raise SourceSyncError("GitHub issue source is missing a target repository.")

        existing = await self.store.get(
            WorkItem,
            filter={
                "tracker_issue.provider": GITHUB_TRACKER_PROVIDER,
                "tracker_issue.issue_number": issue.number,
            },
        )
        candidate = _work_item_from_issue(source, issue, self.now, existing)
        if not self.apply:
            self._count(self._created if existing is None else self._updated, "work_items")
            return

        saved = await self._insert_or_save("work_items", candidate, existing is not None)
        await self._upsert_workflow_state(saved, issue)

    async def _upsert_workflow_state(self, work_item: WorkItem, issue: GitHubIssueSnapshot) -> None:
        work_item_id = _work_item_id(work_item)
        existing = await self.store.get(WorkflowStateRecord, work_item_id)
        state = _workflow_state_from_work_item(work_item, issue, existing)
        candidate = WorkflowStateRecord(
            id=work_item_id,
            work_item_id=work_item_id,
            state=state,
            created_at=existing.created_at if existing is not None else self.now,
            updated_at=self.now,
            version=existing.version if existing is not None else 0,
            source_provenance=self._provenance(
                source_id=f"github-issue:{work_item.tracker_issue.issue_number}"
                if work_item.tracker_issue is not None
                else "github-issue"
            ),
            public_safety=PublicSafetyClass.PRIVATE_REFERENCE,
            redaction_status=RedactionStatus.NOT_REQUIRED,
        )
        await self._insert_or_save("workflow_states", candidate, existing is not None)

    async def _insert_or_save[T: AntDoc](self, collection: str, record: T, exists: bool) -> T:
        if exists:
            self._count(self._updated, collection)
            return await self.store.save(record)
        self._count(self._created, collection)
        return await self.store.insert(record)

    def _event(self) -> WorkflowEvent:
        if self._event_subject is None:
            raise SourceSyncError("Cannot emit a source-sync event without a source subject.")
        return WorkflowEvent(
            event_type=WorkflowEventType.SOURCE_SYNCED,
            happened_at=self.now,
            actor=ActorRef(actor_type=ActorType.SERVICE, actor_id="github-issue-sync"),
            subject=self._event_subject,
            correlation_id=f"github-issue-sync:{_format_datetime(self.now)}",
            workflow_stage=WorkflowStage.PLANNING,
            risk=RiskLevel.LOW,
            public_safety=PublicSafetyClass.PRIVATE_REFERENCE,
            payload_schema=GITHUB_ISSUE_SYNC_EVENT_SCHEMA,
            payload={
                "source_connections": self.source_connections,
                "fetched_issues": self.fetched_issues,
                "imported_issues": self.imported_issues,
                "skipped_pull_requests": self.skipped_pull_requests,
                "source_observations_created": self._created.get("source_observations", 0),
                "work_items_created": self._created.get("work_items", 0),
                "work_items_updated": self._updated.get("work_items", 0),
                "workflow_states_created": self._created.get("workflow_states", 0),
                "workflow_states_updated": self._updated.get("workflow_states", 0),
            },
            source_provenance=self._provenance(source_id="github-issue-sync"),
            redaction_status=RedactionStatus.NOT_REQUIRED,
            created_at=self.now,
            updated_at=self.now,
        )

    def _provenance(self, *, source_id: str, source_url: str | None = None) -> SourceProvenance:
        return SourceProvenance(
            source_system=SourceSystem.GITHUB,
            source_id=source_id,
            observed_at=self.now,
            source_url=source_url,
            public_safety=PublicSafetyClass.PRIVATE_REFERENCE,
        )

    @staticmethod
    def _count(target: dict[str, int], collection: str) -> None:
        target[collection] = target.get(collection, 0) + 1


def _source_observation(
    source: SourceConnection,
    issue: GitHubIssueSnapshot,
    now: datetime,
) -> SourceObservation:
    payload = _issue_payload(issue)
    content_hash = ContentHash(algorithm="sha256", value=_issue_hash(payload))
    return SourceObservation(
        source_connection_id=_source_id(source),
        external_id=f"issue:{issue.number}",
        content_hash=content_hash,
        summary=f"GitHub issue #{issue.number}: {issue.title}",
        payload_schema=GITHUB_ISSUE_PAYLOAD_SCHEMA,
        payload=payload,
        created_at=now,
        updated_at=now,
        source_provenance=SourceProvenance(
            source_system=SourceSystem.GITHUB,
            source_id=f"github-issue:{issue.number}",
            observed_at=now,
            source_url=issue.html_url,
            external_updated_at=issue.updated_at,
            content_hash=content_hash,
            public_safety=PublicSafetyClass.PRIVATE_REFERENCE,
        ),
        public_safety=PublicSafetyClass.PRIVATE_REFERENCE,
        redaction_status=RedactionStatus.NOT_REQUIRED,
    )


def _work_item_from_issue(
    source: SourceConnection,
    issue: GitHubIssueSnapshot,
    now: datetime,
    existing: WorkItem | None,
) -> WorkItem:
    if source.target_repo is None:
        raise SourceSyncError("GitHub issue source is missing a target repository.")

    report = evaluate_issue_quality(
        IssueQualityInput(
            number=issue.number,
            title=issue.title,
            labels=issue.labels,
            body=issue.body,
            author_association=issue.author_association,
        )
    )
    blocker_summaries = _blocker_summaries(report.findings, report.trust_warnings)
    closed = _issue_closed(issue)
    workflow_stage = WorkflowStage.IMPLEMENTED if closed else WorkflowStage.PLANNING
    status = QueueStatus.DONE if closed else QueueStatus.TODO
    if not closed and blocker_summaries:
        status = QueueStatus.BLOCKED

    return WorkItem(
        id=existing.id if existing is not None else None,
        item_type=_work_item_type(report.issue_type),
        title=issue.title,
        goal=f"Track GitHub issue #{issue.number}: {issue.title}",
        target_repo=source.target_repo,
        tracker_issue=TrackerIssueRef(
            tracker_issue_id=f"issue:{issue.number}",
            provider=GITHUB_TRACKER_PROVIDER,
            issue_number=issue.number,
            title=issue.title,
            url=issue.html_url,
        ),
        workflow_stage=workflow_stage,
        status=status,
        review_route=existing.review_route if existing is not None else ReviewRoute.REVIEW_BOTH,
        risk=report.risk_level,
        quality_status="closed" if closed else _quality_status(blocker_summaries),
        plan_ref=existing.plan_ref if existing is not None else None,
        pull_request_ref=existing.pull_request_ref if existing is not None else None,
        blocker_summaries=() if closed else blocker_summaries,
        evidence_refs=existing.evidence_refs if existing is not None else (),
        created_at=existing.created_at if existing is not None else now,
        updated_at=now,
        version=existing.version if existing is not None else 0,
        source_provenance=SourceProvenance(
            source_system=SourceSystem.GITHUB,
            source_id=f"github-issue:{issue.number}",
            observed_at=now,
            source_url=issue.html_url,
            external_updated_at=issue.updated_at,
            content_hash=ContentHash(algorithm="sha256", value=_issue_hash(_issue_payload(issue))),
            public_safety=PublicSafetyClass.PRIVATE_REFERENCE,
        ),
        public_safety=PublicSafetyClass.PRIVATE_REFERENCE,
        redaction_status=RedactionStatus.NOT_REQUIRED,
    )


def _workflow_state_from_work_item(
    work_item: WorkItem,
    issue: GitHubIssueSnapshot,
    existing: WorkflowStateRecord | None,
) -> WorkflowState:
    blockers = tuple(
        Blocker(
            blocker_id=f"github-issue-quality-{index}",
            summary=summary,
            created_at=issue.updated_at,
        )
        for index, summary in enumerate(work_item.blocker_summaries, start=1)
    )
    lease = (
        None
        if work_item.status == QueueStatus.DONE
        else (existing.state.lease if existing is not None else None)
    )
    return WorkflowState(
        stage=work_item.workflow_stage,
        status=work_item.status,
        review_route=work_item.review_route,
        risk=work_item.risk,
        lease=lease,
        blockers=blockers,
    )


def _issue_payload(issue: GitHubIssueSnapshot) -> dict[str, ObservationScalar]:
    return {
        "issue_number": issue.number,
        "node_id": issue.node_id,
        "title": issue.title,
        "body": issue.body,
        "state": issue.state,
        "url": issue.html_url,
        "labels": ",".join(issue.labels),
        "author_association": issue.author_association,
        "created_at": _format_datetime(issue.created_at),
        "updated_at": _format_datetime(issue.updated_at),
        "closed_at": _format_datetime(issue.closed_at) if issue.closed_at is not None else None,
        "is_pull_request": issue.is_pull_request,
    }


def _issue_hash(payload: Mapping[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    ).hexdigest()


def _blocker_summaries(
    findings: Sequence[IssueQualityFinding],
    trust_warnings: Sequence[IssueQualityFinding],
) -> tuple[str, ...]:
    blocking = [
        finding for finding in (*findings, *trust_warnings) if finding.severity == "blocking"
    ]
    if not blocking:
        return ()
    return tuple(f"{finding.code}: {finding.message}" for finding in blocking)


def _quality_status(blocker_summaries: Sequence[str]) -> str:
    return "blocked" if blocker_summaries else "ready_for_planning"


def _work_item_type(issue_type: str) -> WorkItemType:
    if issue_type == WorkItemType.SPIKE.value:
        return WorkItemType.SPIKE
    return WorkItemType.TASK


def _issue_closed(issue: GitHubIssueSnapshot) -> bool:
    return issue.state.lower() == "closed"


def _cursor_since(value: str) -> datetime | None:
    if value == INITIAL_CURSOR_VALUE:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)


def _next_cursor_value(
    current_value: str,
    issues: Sequence[GitHubIssueSnapshot],
    now: datetime,
) -> str:
    if issues:
        return _format_datetime(max(issue.updated_at for issue in issues))
    if current_value == INITIAL_CURSOR_VALUE:
        return _format_datetime(now)
    return current_value


def _format_datetime(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _source_id(source: SourceConnection) -> ObjectId:
    if not isinstance(source.id, ObjectId):
        raise SourceSyncError("SourceConnection must have an ObjectId before sync.")
    return source.id


def _work_item_id(work_item: WorkItem) -> ObjectId:
    if not isinstance(work_item.id, ObjectId):
        raise SourceSyncError("WorkItem must have an ObjectId before state sync.")
    return work_item.id
