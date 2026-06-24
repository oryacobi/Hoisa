import asyncio
from collections.abc import Coroutine
from datetime import UTC, datetime
from typing import Any

from bson import ObjectId

from hoisa.adapters.persistence.memory import InMemoryStore
from hoisa.app.services.github_connection_bootstrap import (
    GITHUB_WORKFLOW_ACTIONS,
    INITIAL_CURSOR_VALUE,
    GitHubBootstrapRequest,
    GitHubRepoBootstrapMetadata,
    bootstrap_github_repo_connection,
)
from hoisa.domain.sources import SourceConnection, SourceConnectionResourceType, SyncCursor
from hoisa.domain.target_repos import Project, RepositoryVisibility, TargetRepo
from hoisa.domain.tool_control import ToolConnection, ToolPolicy, ToolPolicyDecision


def test_dry_run_validates_without_persisting_records() -> None:
    store = InMemoryStore()

    result = run(
        bootstrap_github_repo_connection(
            request=_request(),
            client=_FakeBootstrapClient(),
            store=store,
            apply=False,
            now=_time(),
        )
    )

    assert result.applied is False
    assert result.redacted_summary()["repository"] == "<redacted>"
    assert run(store.find(Project)) == []


def test_apply_seeds_private_reference_connection_records_idempotently() -> None:
    store = InMemoryStore()

    first = run(
        bootstrap_github_repo_connection(
            request=_request(),
            client=_FakeBootstrapClient(),
            store=store,
            apply=True,
            now=_time(),
        )
    )
    second = run(
        bootstrap_github_repo_connection(
            request=_request(),
            client=_FakeBootstrapClient(),
            store=store,
            apply=True,
            now=_time(1),
        )
    )

    sources = run(store.find(SourceConnection))
    tools = run(store.find(ToolConnection))
    policies = run(store.find(ToolPolicy))
    cursors = run(store.find(SyncCursor))
    repos = run(store.find(TargetRepo))

    assert first.created_counts["source_connections"] == 1
    assert second.updated_counts["source_connections"] == 1
    assert len(sources) == 1
    assert len(tools) == 1
    assert len(repos) == 1
    assert len(policies) == len(GITHUB_WORKFLOW_ACTIONS)
    assert len(cursors) == 1
    assert {cursor.cursor_value for cursor in cursors} == {INITIAL_CURSOR_VALUE}
    assert {policy.decision for policy in policies} == {ToolPolicyDecision.ALLOW}
    assert sources[0].resource_type == SourceConnectionResourceType.GITHUB_REPOSITORY_ISSUES
    assert sources[0].external_node_id is None
    assert sources[0].display_url == "https://github.com/example-org/example-repo"
    assert sources[0].credential_ref == "local:github-example-workflow"
    assert tools[0].credential_ref == "local:github-example-workflow"
    assert isinstance(sources[0].id, ObjectId)


class _FakeBootstrapClient:
    def validate_repository(self, request: GitHubBootstrapRequest) -> GitHubRepoBootstrapMetadata:
        assert request.credential_ref == "local:github-example-workflow"
        return GitHubRepoBootstrapMetadata(
            repo_owner=request.repo_owner,
            repo_name=request.repo_name,
            repo_url="https://github.com/example-org/example-repo",
            repo_default_branch="main",
            repo_visibility=RepositoryVisibility.PRIVATE,
            issue_access_checked=True,
        )


def _request() -> GitHubBootstrapRequest:
    return GitHubBootstrapRequest(
        credential_ref="local:github-example-workflow",
        repo_owner="example-org",
        repo_name="example-repo",
        repo_visibility=RepositoryVisibility.PRIVATE,
        hoisa_project_name="Example Project",
    )


def _time(minutes: int = 0) -> datetime:
    return datetime(2026, 6, 23, 12, minutes, tzinfo=UTC)


def run[T](coro: Coroutine[Any, Any, T]) -> T:
    return asyncio.run(coro)
