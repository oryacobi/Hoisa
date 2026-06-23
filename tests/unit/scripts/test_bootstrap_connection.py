import argparse
import asyncio
from collections.abc import Coroutine
import importlib.util
import json
from pathlib import Path
import sys
from typing import Any

from hoisa.adapters.persistence.memory import InMemoryStore
from hoisa.app.services.github_connection_bootstrap import (
    GitHubBootstrapRequest,
    GitHubRepoBootstrapMetadata,
)
from hoisa.domain.target_repos import RepositoryVisibility


def load_bootstrap_script() -> Any:
    path = Path(__file__).parents[3] / "scripts" / "github" / "bootstrap_connection.py"
    spec = importlib.util.spec_from_file_location("bootstrap_connection", path)
    if spec is None or spec.loader is None:
        raise AssertionError("Could not load bootstrap_connection helper.")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


bootstrap_script = load_bootstrap_script()


def test_bootstrap_script_dry_run_uses_private_manifest_without_store(tmp_path: Path) -> None:
    manifest = _write_manifest(tmp_path)

    result = run(
        bootstrap_script._run(
            _args(manifest, apply=False),
            client=_FakeBootstrapClient(),
        )
    )

    assert result.applied is False
    assert result.redacted_summary()["repository_resolved"] is True


def test_bootstrap_script_apply_accepts_injected_store(tmp_path: Path) -> None:
    manifest = _write_manifest(tmp_path)
    store = InMemoryStore()

    result = run(
        bootstrap_script._run(
            _args(manifest, apply=True),
            client=_FakeBootstrapClient(),
            store=store,
        )
    )

    assert result.applied is True
    assert result.created_counts["projects"] == 1


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


def run[T](coro: Coroutine[Any, Any, T]) -> T:
    return asyncio.run(coro)
