"""GitHub repository bootstrap client."""

import base64
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
import hashlib
import json
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from hoisa.app.services.github_connection_bootstrap import (
    GitHubBootstrapRequest,
    GitHubRepoBootstrapMetadata,
)
from hoisa.domain.credentials import CredentialRef
from hoisa.domain.target_repos import RepositoryVisibility
from hoisa.ports.credentials import CredentialResolver, GitHubAppCredentialMaterial

GITHUB_API_VERSION = "2026-03-10"


class GitHubApiError(RuntimeError):
    """Raised when GitHub validation or authentication fails."""


class GitHubAppInstallationClient:
    """GitHub client authenticated through a GitHub App installation."""

    def __init__(
        self,
        *,
        credential_resolver: CredentialResolver,
        api_base_url: str = "https://api.github.com",
        now: Callable[[], datetime] | None = None,
        timeout_seconds: float = 20,
    ) -> None:
        self.credential_resolver = credential_resolver
        self.api_base_url = api_base_url.rstrip("/")
        self.now = now or (lambda: datetime.now(tz=UTC))
        self.timeout_seconds = timeout_seconds
        self._token_cache: dict[CredentialRef, _InstallationToken] = {}

    def validate_repository(
        self,
        request: GitHubBootstrapRequest,
    ) -> GitHubRepoBootstrapMetadata:
        """Resolve the configured repository, then smoke-test issue reads."""

        token = self._installation_token(request.credential_ref)
        repo = self._request_json(
            "GET",
            f"/repos/{request.repo_owner}/{request.repo_name}",
            token=token,
        )
        if not isinstance(repo, dict):
            raise GitHubApiError("GitHub repository response was not an object.")
        self._check_issue_access(request, token)

        return GitHubRepoBootstrapMetadata(
            repo_owner=request.repo_owner,
            repo_name=request.repo_name,
            repo_url=_string(repo.get("html_url") or repo.get("url")),
            repo_default_branch=_optional_string(repo.get("default_branch")),
            repo_visibility=_repo_visibility(repo, request.repo_visibility),
            issue_access_checked=True,
        )

    def _installation_token(self, credential_ref: CredentialRef) -> str:
        cached = self._token_cache.get(credential_ref)
        now = self.now().astimezone(UTC)
        if cached is not None and cached.expires_at - timedelta(seconds=60) > now:
            return cached.token

        material = self.credential_resolver.resolve_github_app(credential_ref)
        jwt = generate_github_app_jwt(material, now=now)
        payload = self._request_json(
            "POST",
            f"/app/installations/{material.installation_id}/access_tokens",
            bearer=jwt,
        )
        if not isinstance(payload, dict):
            raise GitHubApiError("GitHub installation-token response was not an object.")
        token = _required_string(payload.get("token"), "installation token")
        expires_at = _parse_github_datetime(
            _required_string(payload.get("expires_at"), "installation token expiry")
        )
        self._token_cache[credential_ref] = _InstallationToken(token=token, expires_at=expires_at)
        return token

    def _check_issue_access(self, request: GitHubBootstrapRequest, token: str) -> None:
        payload = self._request_json(
            "GET",
            f"/repos/{request.repo_owner}/{request.repo_name}/issues?state=all&per_page=1",
            token=token,
        )
        if not isinstance(payload, list):
            raise GitHubApiError("GitHub issues smoke check did not return a list.")

    def _request_json(
        self,
        method: str,
        path: str,
        *,
        token: str | None = None,
        bearer: str | None = None,
        body: dict[str, Any] | None = None,
    ) -> Any:
        auth = bearer or token
        if auth is None:
            raise GitHubApiError("GitHub request requires an auth token.")
        data = None if body is None else json.dumps(body).encode("utf-8")
        headers = {
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {auth}",
            "X-GitHub-Api-Version": GITHUB_API_VERSION,
        }
        if data is not None:
            headers["Content-Type"] = "application/json"
        request = Request(  # noqa: S310
            f"{self.api_base_url}{path}",
            data=data,
            headers=headers,
            method=method,
        )
        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:  # noqa: S310
                raw = response.read().decode("utf-8")
        except HTTPError as exc:
            message = exc.read().decode("utf-8", errors="replace")
            raise GitHubApiError(f"GitHub API returned HTTP {exc.code}: {message}") from exc
        except URLError as exc:
            raise GitHubApiError(f"GitHub API request failed: {exc.reason}") from exc
        if not raw:
            return None
        return json.loads(raw)


def generate_github_app_jwt(
    material: GitHubAppCredentialMaterial,
    *,
    now: datetime,
) -> str:
    """Generate a GitHub App JWT using the resolved private key."""

    issued_at = int(now.timestamp()) - 60
    expires_at = issued_at + 600
    header = {"alg": "RS256", "typ": "JWT"}
    payload = {"iat": issued_at, "exp": expires_at, "iss": str(material.app_id)}
    signing_input = ".".join(
        (
            _base64url_json(header),
            _base64url_json(payload),
        )
    ).encode("ascii")
    key = _parse_rsa_private_key(material.private_key_pem)
    signature = _rsa_sha256_sign(signing_input, key)
    return f"{signing_input.decode('ascii')}.{_base64url(signature)}"


class _InstallationToken:
    def __init__(self, *, token: str, expires_at: datetime) -> None:
        self.token = token
        self.expires_at = expires_at


class _RsaPrivateKey:
    def __init__(self, *, modulus: int, private_exponent: int) -> None:
        self.modulus = modulus
        self.private_exponent = private_exponent


class _DerReader:
    def __init__(self, data: bytes) -> None:
        self.data = data
        self.position = 0

    def done(self) -> bool:
        return self.position == len(self.data)

    def sequence(self) -> "_DerReader":
        return _DerReader(self._read_tlv(0x30))

    def integer(self) -> int:
        value = self._read_tlv(0x02)
        return int.from_bytes(value, "big", signed=False)

    def octet_string(self) -> bytes:
        return self._read_tlv(0x04)

    def skip(self) -> None:
        if self.done():
            raise GitHubApiError("Unexpected end of DER key.")
        tag = self.data[self.position]
        self._read_tlv(tag)

    def _read_tlv(self, expected_tag: int) -> bytes:
        if self.position >= len(self.data) or self.data[self.position] != expected_tag:
            raise GitHubApiError("Unsupported RSA private key format.")
        self.position += 1
        length = self._read_length()
        end = self.position + length
        if end > len(self.data):
            raise GitHubApiError("Truncated RSA private key.")
        value = self.data[self.position : end]
        self.position = end
        return value

    def _read_length(self) -> int:
        if self.position >= len(self.data):
            raise GitHubApiError("Truncated RSA private key length.")
        first = self.data[self.position]
        self.position += 1
        if first < 0x80:
            return first
        size = first & 0x7F
        if size == 0 or size > 4 or self.position + size > len(self.data):
            raise GitHubApiError("Unsupported RSA private key length.")
        value = int.from_bytes(self.data[self.position : self.position + size], "big")
        self.position += size
        return value


def _parse_rsa_private_key(pem: str) -> _RsaPrivateKey:
    der = _pem_to_der(pem)
    outer = _DerReader(der).sequence()
    outer.integer()
    if not outer.done():
        maybe_pkcs1 = _try_read_pkcs1_key(outer)
        if maybe_pkcs1 is not None:
            return maybe_pkcs1

    outer = _DerReader(der).sequence()
    outer.integer()
    outer.skip()
    private_key = outer.octet_string()
    return _read_pkcs1_key(_DerReader(private_key).sequence())


def _try_read_pkcs1_key(reader: _DerReader) -> _RsaPrivateKey | None:
    try:
        modulus = reader.integer()
        public_exponent = reader.integer()
        private_exponent = reader.integer()
    except GitHubApiError:
        return None
    _ = public_exponent
    return _RsaPrivateKey(modulus=modulus, private_exponent=private_exponent)


def _read_pkcs1_key(sequence: _DerReader) -> _RsaPrivateKey:
    sequence.integer()
    modulus = sequence.integer()
    sequence.integer()
    private_exponent = sequence.integer()
    return _RsaPrivateKey(modulus=modulus, private_exponent=private_exponent)


def _pem_to_der(pem: str) -> bytes:
    lines = [
        line.strip() for line in pem.splitlines() if line.strip() and not line.startswith("-----")
    ]
    if not lines:
        raise GitHubApiError("Private key PEM has no body.")
    return base64.b64decode("".join(lines), validate=True)


def _rsa_sha256_sign(message: bytes, key: _RsaPrivateKey) -> bytes:
    digest = hashlib.sha256(message).digest()
    digest_info = bytes.fromhex("3031300d060960864801650304020105000420") + digest
    key_size = (key.modulus.bit_length() + 7) // 8
    padding_length = key_size - len(digest_info) - 3
    if padding_length < 8:
        raise GitHubApiError("RSA private key is too small for RS256.")
    encoded = b"\x00\x01" + (b"\xff" * padding_length) + b"\x00" + digest_info
    signature_int = pow(
        int.from_bytes(encoded, "big"),
        key.private_exponent,
        key.modulus,
    )
    return signature_int.to_bytes(key_size, "big")


def _repo_visibility(
    repo: dict[str, Any],
    fallback: RepositoryVisibility,
) -> RepositoryVisibility:
    raw = _string(repo.get("visibility"))
    if raw:
        try:
            return RepositoryVisibility(raw)
        except ValueError:
            pass
    if repo.get("private") is True:
        return RepositoryVisibility.PRIVATE
    if repo.get("private") is False:
        return RepositoryVisibility.PUBLIC
    return fallback


def _parse_github_datetime(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)


def _base64url_json(value: dict[str, Any]) -> str:
    return _base64url(json.dumps(value, separators=(",", ":"), sort_keys=True).encode("utf-8"))


def _base64url(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _required_string(value: Any, label: str) -> str:
    text = _string(value)
    if not text:
        raise GitHubApiError(f"Missing {label} in GitHub response.")
    return text


def _optional_string(value: Any) -> str | None:
    text = _string(value)
    return text or None


def _string(value: Any) -> str:
    return value if isinstance(value, str) else ""
