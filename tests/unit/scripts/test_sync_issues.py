import argparse
import asyncio
from collections.abc import Coroutine
from datetime import UTC, datetime
import importlib.util
import json
from pathlib import Path
import sys
from typing import Any

from hoisa.adapters.persistence.memory import InMemoryStore
from hoisa.app.services.github_connection_bootstrap import (
    GitHubBootstrapRequest,
    GitHubRepoBootstrapMetadata,
    bootstrap_github_repo_connection,
)
from hoisa.domain.sources import SourceObservation
from hoisa.domain.target_repos import RepositoryVisibility
from hoisa.domain.work_items import WorkItem
from hoisa.ports.source_sync import GitHubIssueSnapshot, GitHubIssueSyncRequest


def load_sync_script() -> Any:
    path = Path(__file__).parents[3] / "scripts" / "github" / "sync_issues.py"
    spec = importlib.util.spec_from_file_location("sync_issues", path)
    if spec is None or spec.loader is None:
        raise AssertionError("Could not load sync_issues helper.")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


sync_script = load_sync_script()


def test_sync_script_dry_run_fetches_without_store(tmp_path: Path) -> None:
    manifest = _write_manifest(tmp_path)

    result = run(
        sync_script._run(
            _args(manifest, apply=False),
            client=_FakeIssueClient((_issue(1), _issue(2, is_pull_request=True))),
        )
    )

    assert result.applied is False
    assert result.imported_issues == 1
    assert result.created_counts["source_observations"] == 1


def test_sync_script_apply_accepts_injected_store(tmp_path: Path) -> None:
    manifest = _write_manifest(tmp_path)
    store = InMemoryStore()
    run(
        bootstrap_github_repo_connection(
            request=_request(),
            client=_FakeBootstrapClient(),
            store=store,
            apply=True,
            now=_time(),
        )
    )

    result = run(
        sync_script._run(
            _args(manifest, apply=True),
            client=_FakeIssueClient((_issue(1),)),
            store=store,
        )
    )

    assert result.applied is True
    assert result.created_counts["source_observations"] == 1
    assert len(run(store.find(SourceObservation))) == 1
    assert len(run(store.find(WorkItem))) == 1


class _FakeIssueClient:
    def __init__(self, issues: tuple[GitHubIssueSnapshot, ...]) -> None:
        self.issues = issues

    def list_repository_issues(
        self,
        request: GitHubIssueSyncRequest,
    ) -> tuple[GitHubIssueSnapshot, ...]:
        assert request.credential_ref == "local:github-example-workflow"
        return self.issues


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


def _write_manifest(tmp_path: Path) -> Path:
    path = tmp_path / "hoisa.json"
    path.write_text(
        json.dumps(
            {
                "credential_ref": "local:github-example-workflow",
                "app_id": 123,
                "installation_id": 456,
                "private_key_file": "github-app.pem",
                "repo_owner": "example-org",
                "repo_name": "example-repo",
                "hoisa_project_name": "Example Project",
            }
        ),
        encoding="utf-8",
    )
    return path


def _args(path: Path, *, apply: bool) -> argparse.Namespace:
    return argparse.Namespace(
        config=path,
        apply=apply,
        mongo_uri="",
        mongo_database="",
    )


def _request() -> GitHubBootstrapRequest:
    return GitHubBootstrapRequest(
        credential_ref="local:github-example-workflow",
        repo_owner="example-org",
        repo_name="example-repo",
        repo_visibility=RepositoryVisibility.PRIVATE,
        hoisa_project_name="Example Project",
    )


def _issue(number: int, *, is_pull_request: bool = False) -> GitHubIssueSnapshot:
    return GitHubIssueSnapshot(
        number=number,
        node_id=f"I_{number}",
        title=f"Issue {number}",
        body=_task_body(),
        state="open",
        html_url=f"https://github.com/example-org/example-repo/issues/{number}",
        labels=(),
        author_association="OWNER",
        created_at=_time(),
        updated_at=_time(number),
        is_pull_request=is_pull_request,
    )


def _task_body() -> str:
    return """## Goal
Do the thing.

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
