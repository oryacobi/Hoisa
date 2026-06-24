"""Bootstrap GitHub repository issue connections into Hoisa's durable records."""

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Protocol

from antonic import AntDoc
from bson import ObjectId

from hoisa.domain.credentials import CredentialRef
from hoisa.domain.privacy import PublicSafetyClass, RedactionStatus
from hoisa.domain.provenance import SourceProvenance, SourceSystem
from hoisa.domain.sources import (
    SourceConnection,
    SourceConnectionResourceType,
    SourceConnectionStatus,
    SyncCursor,
)
from hoisa.domain.target_repos import (
    Project,
    ProjectRef,
    RepositoryProvider,
    RepositoryVisibility,
    TargetRepo,
    TargetRepoRef,
)
from hoisa.domain.tool_control import (
    ToolConnection,
    ToolConnectionStatus,
    ToolPolicy,
    ToolPolicyDecision,
)
from hoisa.ports.persistence import (
    PersistenceStore,
    SyncCursorKey,
    sync_cursor_filter,
    target_repo_filter,
)

GITHUB_TOOL_TYPE = "github"
GITHUB_WORKFLOW_ACTIONS = (
    "read_repository_metadata",
    "push_code",
    "read_issues",
    "create_issues",
    "update_issue_metadata",
    "comment_on_issues_and_prs",
    "manage_issue_labels",
    "manage_issue_assignees",
    "read_pull_requests",
    "create_pull_requests",
    "update_pull_requests",
    "comment_on_pull_requests",
    "review_pull_requests",
    "reply_to_pull_request_review_comments",
    "read_pull_request_files_and_diffs",
    "read_checks_and_statuses",
    "write_checks_and_statuses",
    "read_actions",
    "rerun_or_cancel_actions",
    "update_workflow_files",
)
INITIAL_CURSOR_VALUE = "not_started"


@dataclass(frozen=True, slots=True)
class GitHubBootstrapRequest:
    """Public-safe repository connection details read from a private manifest."""

    credential_ref: CredentialRef
    repo_owner: str
    repo_name: str
    repo_visibility: RepositoryVisibility
    hoisa_project_name: str | None = None

    @property
    def project_name(self) -> str:
        """Return the Hoisa project name to store."""

        return self.hoisa_project_name or f"{self.repo_owner}/{self.repo_name}"


@dataclass(frozen=True, slots=True)
class GitHubRepoBootstrapMetadata:
    """Resolved GitHub repository facts used to seed durable records."""

    repo_owner: str
    repo_name: str
    repo_url: str
    repo_default_branch: str | None
    repo_visibility: RepositoryVisibility
    issue_access_checked: bool


class GitHubRepoBootstrapClient(Protocol):
    """GitHub client used by the repo bootstrap service."""

    def validate_repository(
        self,
        request: GitHubBootstrapRequest,
    ) -> GitHubRepoBootstrapMetadata:
        """Resolve and validate the configured GitHub repository."""
        ...


@dataclass(frozen=True, slots=True)
class GitHubBootstrapResult:
    """Result of validating or applying a GitHub bootstrap manifest."""

    applied: bool
    metadata: GitHubRepoBootstrapMetadata
    created_counts: Mapping[str, int]
    updated_counts: Mapping[str, int]

    def redacted_summary(self) -> dict[str, Any]:
        """Return a safe summary for operator output."""

        return {
            "applied": self.applied,
            "auth": "github_app_installation",
            "credential_ref": "<configured>",
            "repository": "<redacted>",
            "repository_resolved": True,
            "issue_access_checked": self.metadata.issue_access_checked,
            "created": dict(self.created_counts),
            "updated": dict(self.updated_counts),
        }


async def bootstrap_github_repo_connection(
    *,
    request: GitHubBootstrapRequest,
    client: GitHubRepoBootstrapClient,
    store: PersistenceStore | None = None,
    apply: bool = False,
    now: datetime | None = None,
) -> GitHubBootstrapResult:
    """Validate a GitHub repository connection and optionally seed durable records."""

    metadata = client.validate_repository(request)
    if not apply:
        return GitHubBootstrapResult(
            applied=False,
            metadata=metadata,
            created_counts={},
            updated_counts={},
        )
    if store is None:
        raise ValueError("A persistence store is required when apply=True.")

    timestamp = (now or datetime.now(tz=UTC)).astimezone(UTC)
    writer = _BootstrapWriter(store, request, metadata, timestamp)
    await writer.apply()
    return GitHubBootstrapResult(
        applied=True,
        metadata=metadata,
        created_counts=writer.created_counts,
        updated_counts=writer.updated_counts,
    )


class _BootstrapWriter:
    def __init__(
        self,
        store: PersistenceStore,
        request: GitHubBootstrapRequest,
        metadata: GitHubRepoBootstrapMetadata,
        now: datetime,
    ) -> None:
        self.store = store
        self.request = request
        self.metadata = metadata
        self.now = now
        self._created: dict[str, int] = {}
        self._updated: dict[str, int] = {}

    @property
    def created_counts(self) -> Mapping[str, int]:
        return self._created

    @property
    def updated_counts(self) -> Mapping[str, int]:
        return self._updated

    async def apply(self) -> None:
        project = await self._upsert_project()
        project_ref = _project_ref(project)
        repo = await self._upsert_target_repo(project_ref)
        repo_ref = _target_repo_ref(repo)
        source = await self._upsert_source_connection(project_ref, repo_ref)
        await self._upsert_tool_connection(project_ref)
        await self._upsert_workflow_policies(project_ref)
        await self._upsert_sync_cursors(_record_id(source))

    async def _upsert_project(self) -> Project:
        existing = await self.store.get(Project, filter={"name": self.request.project_name})
        next_record = Project(
            id=existing.id if existing is not None else None,
            name=self.request.project_name,
            summary="GitHub-backed Hoisa project connection.",
            created_at=existing.created_at if existing is not None else self.now,
            updated_at=self.now,
            version=existing.version if existing is not None else 0,
            source_provenance=self._provenance(source_id="github-repo-bootstrap"),
            public_safety=PublicSafetyClass.PRIVATE_REFERENCE,
            redaction_status=RedactionStatus.NOT_REQUIRED,
        )
        return await self._insert_or_save("projects", next_record, existing is not None)

    async def _upsert_target_repo(self, project: ProjectRef) -> TargetRepo:
        candidate = TargetRepo(
            provider=RepositoryProvider.GITHUB,
            owner=self.metadata.repo_owner,
            name=self.metadata.repo_name,
            visibility=self.metadata.repo_visibility,
            project=project,
            default_branch=self.metadata.repo_default_branch,
            created_at=self.now,
            updated_at=self.now,
            source_provenance=self._provenance(
                source_id=f"github-repo:{self.metadata.repo_owner}/{self.metadata.repo_name}",
                source_url=self.metadata.repo_url,
            ),
            public_safety=PublicSafetyClass.PRIVATE_REFERENCE,
            redaction_status=RedactionStatus.NOT_REQUIRED,
        )
        existing = await self.store.get(TargetRepo, filter=target_repo_filter(candidate))
        if existing is not None:
            candidate = candidate.model_copy(
                update={
                    "id": existing.id,
                    "created_at": existing.created_at,
                    "version": existing.version,
                }
            )
        return await self._insert_or_save("target_repos", candidate, existing is not None)

    async def _upsert_source_connection(
        self,
        project: ProjectRef,
        repo: TargetRepoRef,
    ) -> SourceConnection:
        filters = {
            "project.project_id": project.project_id,
            "source_system": SourceSystem.GITHUB,
            "resource_type": SourceConnectionResourceType.GITHUB_REPOSITORY_ISSUES,
            "target_repo.target_repo_id": repo.target_repo_id,
        }
        existing = await self.store.get(SourceConnection, filter=filters)
        candidate = SourceConnection(
            id=existing.id if existing is not None else None,
            project=project,
            source_system=SourceSystem.GITHUB,
            display_name="GitHub repository issues",
            status=SourceConnectionStatus.ACTIVE,
            target_repo=repo,
            resource_type=SourceConnectionResourceType.GITHUB_REPOSITORY_ISSUES,
            external_node_id=None,
            display_url=self.metadata.repo_url,
            credential_ref=self.request.credential_ref,
            created_at=existing.created_at if existing is not None else self.now,
            updated_at=self.now,
            version=existing.version if existing is not None else 0,
            source_provenance=self._provenance(
                source_id=f"github-repo-issues:{self.metadata.repo_owner}/{self.metadata.repo_name}",
                source_url=self.metadata.repo_url,
            ),
            public_safety=PublicSafetyClass.PRIVATE_REFERENCE,
            redaction_status=RedactionStatus.NOT_REQUIRED,
        )
        return await self._insert_or_save(
            "source_connections",
            candidate,
            existing is not None,
        )

    async def _upsert_tool_connection(self, project: ProjectRef) -> ToolConnection:
        filters = {
            "project.project_id": project.project_id,
            "tool_type": GITHUB_TOOL_TYPE,
            "display_name": "GitHub workflow",
        }
        existing = await self.store.get(ToolConnection, filter=filters)
        candidate = ToolConnection(
            id=existing.id if existing is not None else None,
            project=project,
            tool_type=GITHUB_TOOL_TYPE,
            display_name="GitHub workflow",
            status=ToolConnectionStatus.ACTIVE,
            credential_ref=self.request.credential_ref,
            allowed_action_summaries=(
                "read repository metadata",
                "push code and branches",
                "read issues",
                "create and update issues",
                "post issue and pull request comments",
                "manage labels and assignees",
                "create and update pull requests",
                "submit pull request reviews and replies",
                "read pull request files, diffs, checks, and workflow state",
                "rerun or cancel workflow runs",
                "update workflow files",
            ),
            created_at=existing.created_at if existing is not None else self.now,
            updated_at=self.now,
            version=existing.version if existing is not None else 0,
            source_provenance=self._provenance(source_id="github-tool:workflow"),
            public_safety=PublicSafetyClass.PRIVATE_REFERENCE,
            redaction_status=RedactionStatus.NOT_REQUIRED,
        )
        return await self._insert_or_save(
            "tool_connections",
            candidate,
            existing is not None,
        )

    async def _upsert_workflow_policies(self, project: ProjectRef) -> None:
        for action_type in GITHUB_WORKFLOW_ACTIONS:
            filters = {
                "project.project_id": project.project_id,
                "tool_type": GITHUB_TOOL_TYPE,
                "action_type": action_type,
            }
            existing = await self.store.get(ToolPolicy, filter=filters)
            candidate = ToolPolicy(
                id=existing.id if existing is not None else None,
                project=project,
                tool_type=GITHUB_TOOL_TYPE,
                action_type=action_type,
                decision=ToolPolicyDecision.ALLOW,
                summary=f"Allow GitHub workflow action: {action_type}.",
                created_at=existing.created_at if existing is not None else self.now,
                updated_at=self.now,
                version=existing.version if existing is not None else 0,
                source_provenance=self._provenance(source_id=f"github-policy:{action_type}"),
                public_safety=PublicSafetyClass.PRIVATE_REFERENCE,
                redaction_status=RedactionStatus.NOT_REQUIRED,
            )
            await self._insert_or_save("tool_policies", candidate, existing is not None)

    async def _upsert_sync_cursors(self, source_connection_id: ObjectId) -> None:
        for cursor_name in ("issues",):
            filters = sync_cursor_filter(
                SyncCursorKey(source_connection_id=source_connection_id, cursor_name=cursor_name)
            )
            existing = await self.store.get(SyncCursor, filter=filters)
            if existing is not None:
                continue
            cursor = SyncCursor(
                source_connection_id=source_connection_id,
                cursor_name=cursor_name,
                cursor_value=INITIAL_CURSOR_VALUE,
                created_at=self.now,
                updated_at=self.now,
                source_provenance=self._provenance(source_id=f"github-cursor:{cursor_name}"),
                public_safety=PublicSafetyClass.PRIVATE_REFERENCE,
                redaction_status=RedactionStatus.NOT_REQUIRED,
            )
            await self._insert_or_save("sync_cursors", cursor, exists=False)

    async def _insert_or_save[T: AntDoc](self, collection: str, record: T, exists: bool) -> T:
        if exists:
            self._updated[collection] = self._updated.get(collection, 0) + 1
            return await self.store.save(record)
        self._created[collection] = self._created.get(collection, 0) + 1
        return await self.store.insert(record)

    def _provenance(self, *, source_id: str, source_url: str | None = None) -> SourceProvenance:
        return SourceProvenance(
            source_system=SourceSystem.GITHUB,
            source_id=source_id,
            observed_at=self.now,
            source_url=source_url,
            public_safety=PublicSafetyClass.PRIVATE_REFERENCE,
        )


def _project_ref(project: Project) -> ProjectRef:
    return ProjectRef(project_id=_record_id(project), name=project.name)


def _target_repo_ref(target_repo: TargetRepo) -> TargetRepoRef:
    return TargetRepoRef(
        target_repo_id=_record_id(target_repo),
        provider=target_repo.provider,
        owner=target_repo.owner,
        name=target_repo.name,
        visibility=target_repo.visibility,
        project=target_repo.project,
    )


def _record_id(record: Project | TargetRepo | SourceConnection) -> ObjectId:
    if not isinstance(record.id, ObjectId):
        raise ValueError(f"{type(record).__name__} must have an ObjectId after persistence.")
    return record.id
