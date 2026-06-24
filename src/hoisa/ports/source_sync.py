"""External source synchronization port definitions."""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from hoisa.domain.credentials import CredentialRef


class SourceSyncError(RuntimeError):
    """Raised when an external source cannot be synchronized safely."""


@dataclass(frozen=True, slots=True)
class GitHubIssueSyncRequest:
    """Read-only request for repository issues from a GitHub source."""

    credential_ref: CredentialRef
    repo_owner: str
    repo_name: str
    since: datetime | None = None


@dataclass(frozen=True, slots=True)
class GitHubIssueSnapshot:
    """Public-safe GitHub issue facts used by source sync."""

    number: int
    node_id: str
    title: str
    body: str
    state: str
    html_url: str
    labels: tuple[str, ...]
    author_association: str
    created_at: datetime
    updated_at: datetime
    closed_at: datetime | None = None
    is_pull_request: bool = False


class GitHubIssueSourceClient(Protocol):
    """Read-only GitHub issue source used by Hoisa source sync."""

    def list_repository_issues(
        self,
        request: GitHubIssueSyncRequest,
    ) -> Sequence[GitHubIssueSnapshot]:
        """Return repository issue snapshots for the request."""
        ...
