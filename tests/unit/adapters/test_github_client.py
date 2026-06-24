import base64
from datetime import UTC, datetime
import json
from typing import Any, cast

from hoisa.adapters.external_sources.github import (
    GitHubApiError,
    GitHubAppInstallationClient,
    generate_github_app_jwt,
)
from hoisa.app.services.github_connection_bootstrap import (
    GitHubBootstrapRequest,
)
from hoisa.domain.target_repos import RepositoryVisibility
from hoisa.ports.credentials import GitHubAppCredentialMaterial
from hoisa.ports.source_sync import GitHubIssueSyncRequest


def test_generate_github_app_jwt_uses_app_id_and_short_expiry() -> None:
    material = _credential_material()
    token = generate_github_app_jwt(
        material,
        now=datetime(2026, 6, 23, 12, 0, tzinfo=UTC),
    )

    header, payload, signature = token.split(".")

    assert _decode_json(header)["alg"] == "RS256"
    assert _decode_json(payload) == {
        "exp": 1782216540,
        "iat": 1782215940,
        "iss": "123",
    }
    assert signature


def test_github_app_client_validates_repo_issues_and_caches_installation_token() -> None:
    client = _FakeGitHubClient()
    request = _request()

    metadata = client.validate_repository(request)
    client.validate_repository(request)

    assert metadata.repo_url == "https://github.com/example-org/example-repo"
    assert metadata.repo_default_branch == "main"
    assert metadata.issue_access_checked is True
    assert [call["path"] for call in client.calls].count(
        "/app/installations/456/access_tokens"
    ) == 1
    assert all(call.get("token") != client.installation_access for call in client.calls[:1])
    assert "/graphql" not in [call["path"] for call in client.calls]


def test_github_app_client_rejects_unexpected_issues_response() -> None:
    client = _FakeGitHubClient(issue_response={"message": "nope"})

    try:
        client.validate_repository(_request())
    except GitHubApiError as exc:
        assert "issues smoke check" in str(exc)
    else:
        raise AssertionError("Expected invalid issue response to fail validation.")


def test_github_app_client_lists_repository_issues_with_pagination_since_and_pr_filtering() -> None:
    first_page = (
        *(_raw_issue(number) for number in range(1, 100)),
        _raw_issue(100, pull_request=True),
    )
    second_page = (_raw_issue(101),)
    client = _FakeGitHubClient(issue_pages=(first_page, second_page))

    issues = client.list_repository_issues(
        GitHubIssueSyncRequest(
            credential_ref="local:github-example-workflow",
            repo_owner="example-org",
            repo_name="example-repo",
            since=datetime(2026, 6, 23, 12, 5, tzinfo=UTC),
        )
    )

    paths = [call["path"] for call in client.calls]

    assert len(issues) == 100
    assert {issue.number for issue in issues} == set(range(1, 100)) | {101}
    assert [call["path"] for call in client.calls].count(
        "/app/installations/456/access_tokens"
    ) == 1
    assert any("page=1" in path and "since=2026-06-23T12%3A05%3A00Z" in path for path in paths)
    assert any("page=2" in path for path in paths)


class _FakeResolver:
    def resolve_github_app(self, credential_ref: str) -> GitHubAppCredentialMaterial:
        assert credential_ref == "local:github-example-workflow"
        return _credential_material()


class _FakeGitHubClient(GitHubAppInstallationClient):
    def __init__(
        self,
        *,
        issue_response: Any = None,
        issue_pages: tuple[tuple[dict[str, Any], ...], ...] = (),
    ) -> None:
        super().__init__(
            credential_resolver=_FakeResolver(),
            now=lambda: datetime(2026, 6, 23, 12, 0, tzinfo=UTC),
        )
        self.issue_response = [] if issue_response is None else issue_response
        self.issue_pages = issue_pages
        self.installation_access = "fake-installation-access"
        self.calls: list[dict[str, Any]] = []

    def _request_json(
        self,
        method: str,
        path: str,
        *,
        token: str | None = None,
        bearer: str | None = None,
        body: dict[str, Any] | None = None,
    ) -> Any:
        self.calls.append(
            {
                "method": method,
                "path": path,
                "token": token,
                "bearer": bearer,
                "body": body,
            }
        )
        if path == "/app/installations/456/access_tokens":
            assert bearer is not None and bearer.count(".") == 2
            return {
                "token": self.installation_access,
                "expires_at": "2026-06-23T13:00:00Z",
            }
        if path == "/repos/example-org/example-repo":
            assert token == self.installation_access
            return {
                "html_url": "https://github.com/example-org/example-repo",
                "default_branch": "main",
                "visibility": "private",
            }
        if path == "/repos/example-org/example-repo/issues?state=all&per_page=1":
            assert token == self.installation_access
            return self.issue_response
        if path.startswith("/repos/example-org/example-repo/issues?"):
            assert token == self.installation_access
            page = 1
            if "page=2" in path:
                page = 2
            if not self.issue_pages:
                return []
            return list(self.issue_pages[page - 1])
        raise AssertionError(f"Unexpected GitHub path: {path}")


def _raw_issue(number: int, *, pull_request: bool = False) -> dict[str, Any]:
    raw: dict[str, Any] = {
        "id": number,
        "node_id": f"I_{number}",
        "number": number,
        "title": f"Issue {number}",
        "body": f"Body {number}",
        "state": "open",
        "html_url": f"https://github.com/example-org/example-repo/issues/{number}",
        "labels": [{"name": "type:task"}, "agent:codex"],
        "author_association": "OWNER",
        "created_at": "2026-06-23T12:00:00Z",
        "updated_at": f"2026-06-23T12:{number % 60:02d}:00Z",
        "closed_at": None,
    }
    if pull_request:
        raw["pull_request"] = {"url": "https://api.github.com/pulls/100"}
    return raw


def _request() -> GitHubBootstrapRequest:
    return GitHubBootstrapRequest(
        credential_ref="local:github-example-workflow",
        repo_owner="example-org",
        repo_name="example-repo",
        repo_visibility=RepositoryVisibility.PRIVATE,
        hoisa_project_name="Example Project",
    )


def _credential_material() -> GitHubAppCredentialMaterial:
    return GitHubAppCredentialMaterial(
        credential_ref="local:github-example-workflow",
        app_id=123,
        installation_id=456,
        private_key_pem=_fake_rsa_private_key_pem(),
    )


def _fake_rsa_private_key_pem() -> str:
    modulus = (1 << 511) + 123456789
    private_exponent = 65537
    der = _der_sequence(
        _der_integer(0),
        _der_integer(modulus),
        _der_integer(65537),
        _der_integer(private_exponent),
    )
    body = base64.encodebytes(der).decode("ascii")
    return f"-----BEGIN RSA PRIVATE KEY-----\n{body}-----END RSA PRIVATE KEY-----\n"


def _der_sequence(*values: bytes) -> bytes:
    body = b"".join(values)
    return b"\x30" + _der_length(len(body)) + body


def _der_integer(value: int) -> bytes:
    raw = value.to_bytes(max((value.bit_length() + 7) // 8, 1), "big")
    if raw[0] & 0x80:
        raw = b"\x00" + raw
    return b"\x02" + _der_length(len(raw)) + raw


def _der_length(length: int) -> bytes:
    if length < 0x80:
        return bytes((length,))
    raw = length.to_bytes((length.bit_length() + 7) // 8, "big")
    return bytes((0x80 | len(raw),)) + raw


def _decode_json(value: str) -> dict[str, Any]:
    padded = value + ("=" * (-len(value) % 4))
    return cast(dict[str, Any], json.loads(base64.urlsafe_b64decode(padded).decode("utf-8")))
