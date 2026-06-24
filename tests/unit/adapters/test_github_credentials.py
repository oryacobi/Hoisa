import json
from pathlib import Path

from pydantic import ValidationError
import pytest

from hoisa.adapters.filesystem.github_credentials import (
    LocalGitHubAppCredentialResolver,
    load_github_bootstrap_manifest,
)
from hoisa.ports.credentials import CredentialResolutionError


def test_manifest_loads_bootstrap_request_without_key_material(tmp_path: Path) -> None:
    path = _manifest_path(tmp_path)
    _write_manifest(path, private_key_file="github-app.pem")

    manifest = load_github_bootstrap_manifest(path)
    request = manifest.bootstrap_request()

    assert request.credential_ref == "local:github-example-workflow"
    assert request.repo_name == "example-repo"
    assert request.project_name == "Example Hoisa Project"
    assert manifest.private_key_file == "github-app.pem"


def test_manifest_rejects_private_key_paths(tmp_path: Path) -> None:
    path = _manifest_path(tmp_path)
    _write_manifest(path, private_key_file="../github-app.pem")

    with pytest.raises(ValidationError):
        load_github_bootstrap_manifest(path)


def test_local_resolver_reads_private_key_with_restrictive_permissions(tmp_path: Path) -> None:
    path = _manifest_path(tmp_path)
    key = tmp_path / "github-app.pem"
    key.write_text("-----BEGIN RSA PRIVATE KEY-----\nfake\n-----END RSA PRIVATE KEY-----\n")
    key.chmod(0o600)
    _write_manifest(path, private_key_file=key.name)

    resolver = LocalGitHubAppCredentialResolver.from_manifest_file(path)
    material = resolver.resolve_github_app("local:github-example-workflow")

    assert material.app_id == 123
    assert material.installation_id == 456
    assert "PRIVATE KEY" in material.private_key_pem


def test_local_resolver_rejects_group_readable_private_key(tmp_path: Path) -> None:
    path = _manifest_path(tmp_path)
    key = tmp_path / "github-app.pem"
    key.write_text("-----BEGIN RSA PRIVATE KEY-----\nfake\n-----END RSA PRIVATE KEY-----\n")
    key.chmod(0o644)
    _write_manifest(path, private_key_file=key.name)

    resolver = LocalGitHubAppCredentialResolver.from_manifest_file(path)

    with pytest.raises(CredentialResolutionError, match="group/world"):
        resolver.resolve_github_app("local:github-example-workflow")


def _manifest_path(tmp_path: Path) -> Path:
    return tmp_path / "hoisa.json"


def _write_manifest(path: Path, *, private_key_file: str) -> None:
    path.write_text(
        json.dumps(
            {
                "credential_ref": "local:github-example-workflow",
                "app_id": 123,
                "installation_id": 456,
                "private_key_file": private_key_file,
                "repo_owner": "example-org",
                "repo_name": "example-repo",
                "hoisa_project_name": "Example Hoisa Project",
            }
        ),
        encoding="utf-8",
    )
