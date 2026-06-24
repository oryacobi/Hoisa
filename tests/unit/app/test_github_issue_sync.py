import asyncio
from collections.abc import Coroutine
from datetime import UTC, datetime
from typing import Any

import pytest

from hoisa.adapters.persistence.memory import InMemoryStore
from hoisa.app.services.github_connection_bootstrap import (
    INITIAL_CURSOR_VALUE,
    GitHubBootstrapRequest,
    GitHubRepoBootstrapMetadata,
    bootstrap_github_repo_connection,
)
from hoisa.app.services.github_issue_sync import sync_github_repository_issues
from hoisa.domain.events import WorkflowEvent
from hoisa.domain.sources import SourceObservation, SyncCursor
from hoisa.domain.target_repos import RepositoryVisibility
from hoisa.domain.work_items import WorkItem
from hoisa.domain.workflow_event_types import WorkflowEventType
from hoisa.domain.workflow_state import QueueStatus, WorkflowStage, WorkflowStateRecord
from hoisa.ports.source_sync import GitHubIssueSnapshot, GitHubIssueSyncRequest


def test_issue_sync_imports_observations_work_items_states_and_event() -> None:
    store = _seeded_store()
    client = _FakeIssueClient(
        (
            _issue(1, body=_task_body(), updated_at=_time(1)),
            _issue(2, body="Needs structure.", updated_at=_time(2)),
            _issue(3, state="closed", body="Already done.", updated_at=_time(3)),
            _issue(4, is_pull_request=True, updated_at=_time(4)),
        )
    )

    result = run(
        sync_github_repository_issues(
            client=client,
            store=store,
            apply=True,
            now=_time(10),
        )
    )

    observations = run(store.find(SourceObservation))
    work_items = run(store.find(WorkItem, sort=[("tracker_issue.issue_number", 1)]))
    states = run(store.find(WorkflowStateRecord, sort=[("work_item_id", 1)]))
    events = run(store.find(WorkflowEvent))
    cursor = run(store.find(SyncCursor))[0]

    assert result.created_counts["source_observations"] == 3
    assert result.created_counts["work_items"] == 3
    assert result.created_counts["workflow_states"] == 3
    assert result.updated_counts["sync_cursors"] == 1
    assert result.skipped_pull_requests == 1
    assert len(observations) == 3
    assert [item.tracker_issue.issue_number for item in work_items if item.tracker_issue] == [
        1,
        2,
        3,
    ]
    assert work_items[0].workflow_stage == WorkflowStage.PLANNING
    assert work_items[0].status == QueueStatus.TODO
    assert work_items[1].status == QueueStatus.BLOCKED
    assert work_items[1].blocker_summaries
    assert work_items[2].workflow_stage == WorkflowStage.IMPLEMENTED
    assert work_items[2].status == QueueStatus.DONE
    assert {state.id for state in states} == {item.id for item in work_items}
    assert [event.event_type for event in events] == [WorkflowEventType.SOURCE_SYNCED]
    assert cursor.cursor_value == "2026-06-23T12:03:00Z"


def test_issue_sync_rerun_without_changes_does_not_duplicate_current_records() -> None:
    store = _seeded_store()
    client = _FakeIssueClient((_issue(1, body=_task_body(), updated_at=_time(1)),))

    run(sync_github_repository_issues(client=client, store=store, apply=True, now=_time(10)))
    second = run(
        sync_github_repository_issues(
            client=client,
            store=store,
            apply=True,
            now=_time(11),
        )
    )

    assert second.created_counts.get("source_observations", 0) == 0
    assert len(run(store.find(SourceObservation))) == 1
    assert len(run(store.find(WorkItem))) == 1
    assert len(run(store.find(WorkflowStateRecord))) == 1
    assert client.requests[1].since == _time(1)


def test_issue_sync_changed_issue_adds_observation_and_updates_work_item() -> None:
    store = _seeded_store()
    client = _FakeIssueClient(
        (_issue(1, title="Original", body=_task_body(), updated_at=_time(1)),)
    )
    run(sync_github_repository_issues(client=client, store=store, apply=True, now=_time(10)))

    client.issues = (
        _issue(1, title="Updated", body=_task_body("Updated goal."), updated_at=_time(2)),
    )
    result = run(
        sync_github_repository_issues(
            client=client,
            store=store,
            apply=True,
            now=_time(11),
        )
    )

    work_item = run(store.find(WorkItem))[0]

    assert result.created_counts["source_observations"] == 1
    assert result.updated_counts["work_items"] == 1
    assert len(run(store.find(SourceObservation))) == 2
    assert work_item.title == "Updated"


def test_issue_sync_failure_does_not_advance_cursor() -> None:
    store = _FailingWorkItemStore()
    _seed_store(store)
    client = _FakeIssueClient((_issue(1, body=_task_body(), updated_at=_time(1)),))
    cursor_before = run(store.find(SyncCursor))[0]

    with pytest.raises(RuntimeError, match="work item insert failed"):
        run(sync_github_repository_issues(client=client, store=store, apply=True, now=_time(10)))

    cursor_after = run(store.find(SyncCursor))[0]

    assert cursor_before.cursor_value == INITIAL_CURSOR_VALUE
    assert cursor_after.cursor_value == INITIAL_CURSOR_VALUE


class _FakeIssueClient:
    def __init__(self, issues: tuple[GitHubIssueSnapshot, ...]) -> None:
        self.issues = issues
        self.requests: list[GitHubIssueSyncRequest] = []

    def list_repository_issues(
        self,
        request: GitHubIssueSyncRequest,
    ) -> tuple[GitHubIssueSnapshot, ...]:
        self.requests.append(request)
        if request.since is None:
            return self.issues
        return tuple(issue for issue in self.issues if issue.updated_at > request.since)


class _FailingWorkItemStore(InMemoryStore):
    async def insert(self, ant_doc: Any, *, mongo_options: Any = None) -> Any:
        if isinstance(ant_doc, WorkItem):
            raise RuntimeError("work item insert failed")
        return await super().insert(ant_doc, mongo_options=mongo_options)


class _FakeBootstrapClient:
    def validate_repository(self, request: GitHubBootstrapRequest) -> GitHubRepoBootstrapMetadata:
        return GitHubRepoBootstrapMetadata(
            repo_owner=request.repo_owner,
            repo_name=request.repo_name,
            repo_url="https://github.com/example-org/example-repo",
            repo_default_branch="main",
            repo_visibility=RepositoryVisibility.PRIVATE,
            issue_access_checked=True,
        )


def _seeded_store() -> InMemoryStore:
    store = InMemoryStore()
    _seed_store(store)
    return store


def _seed_store(store: InMemoryStore) -> None:
    run(
        bootstrap_github_repo_connection(
            request=GitHubBootstrapRequest(
                credential_ref="local:github-example-workflow",
                repo_owner="example-org",
                repo_name="example-repo",
                repo_visibility=RepositoryVisibility.PRIVATE,
                hoisa_project_name="Example Project",
            ),
            client=_FakeBootstrapClient(),
            store=store,
            apply=True,
            now=_time(),
        )
    )


def _issue(
    number: int,
    *,
    title: str | None = None,
    body: str = "",
    state: str = "open",
    updated_at: datetime | None = None,
    is_pull_request: bool = False,
) -> GitHubIssueSnapshot:
    return GitHubIssueSnapshot(
        number=number,
        node_id=f"I_{number}",
        title=title or f"Issue {number}",
        body=body,
        state=state,
        html_url=f"https://github.com/example-org/example-repo/issues/{number}",
        labels=(),
        author_association="OWNER",
        created_at=_time(),
        updated_at=updated_at or _time(number),
        closed_at=updated_at if state == "closed" else None,
        is_pull_request=is_pull_request,
    )


def _task_body(goal: str = "Do the thing.") -> str:
    return f"""## Goal
{goal}

## Context and likely files
Use sample files.

## Acceptance criteria
It works.

## Out of scope
Anything else.

## Required checks
pytest
"""


def _time(minutes: int = 0) -> datetime:
    return datetime(2026, 6, 23, 12, minutes, tzinfo=UTC)


def run[T](coro: Coroutine[Any, Any, T]) -> T:
    return asyncio.run(coro)
