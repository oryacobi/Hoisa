"""Ports for resolving private credential references at runtime."""

from dataclasses import dataclass
from typing import Protocol

from hoisa.domain.credentials import CredentialRef


class CredentialResolutionError(RuntimeError):
    """Raised when a private credential reference cannot be resolved."""


@dataclass(frozen=True, slots=True)
class GitHubAppCredentialMaterial:
    """Private GitHub App auth material resolved outside durable records."""

    credential_ref: CredentialRef
    app_id: int
    installation_id: int
    private_key_pem: str


class CredentialResolver(Protocol):
    """Resolve opaque credential refs into private runtime material."""

    def resolve_github_app(self, credential_ref: CredentialRef) -> GitHubAppCredentialMaterial:
        """Return GitHub App material for the requested credential reference."""
        ...
