"""Project and repository references used by Hoisa records."""

from enum import StrEnum
from typing import ClassVar

from antonic import AntIndex
from pydantic import Field

from hoisa.domain.models import ASCENDING, CollectionRoot, HoisaModel
from hoisa.domain.privacy import PublicSafetyClass, RedactionStatus
from hoisa.domain.provenance import SourceProvenance


class RepositoryProvider(StrEnum):
    """Repository host or source provider."""

    GENERIC_GIT = "generic_git"
    GITHUB = "github"


class RepositoryVisibility(StrEnum):
    """Visibility classification for target repository references."""

    PUBLIC = "public"
    PRIVATE = "private"
    INTERNAL = "internal"


class ProjectRef(HoisaModel):
    """Stable reference to a Hoisa project."""

    project_id: str = Field(min_length=1)
    name: str = Field(min_length=1)


class Project(CollectionRoot):
    """Current-state project record stored by persistence adapters."""

    ant_collection: ClassVar[str] = "projects"

    name: str = Field(min_length=1)
    summary: str = Field(min_length=1)
    source_provenance: SourceProvenance
    public_safety: PublicSafetyClass
    redaction_status: RedactionStatus


class TargetRepoRef(HoisaModel):
    """Generic repository reference without local paths or access details."""

    target_repo_id: str = Field(min_length=1)
    provider: RepositoryProvider
    owner: str = Field(min_length=1)
    name: str = Field(min_length=1)
    visibility: RepositoryVisibility
    project: ProjectRef


class TargetRepo(CollectionRoot):
    """Current-state target repository record without local paths or secrets."""

    ant_collection: ClassVar[str] = "target_repos"
    ant_indexes: ClassVar[tuple[AntIndex, ...]] = (
        AntIndex(
            [("provider", ASCENDING), ("owner", ASCENDING), ("name", ASCENDING)],
            unique=True,
            name="uniq_target_repo_provider_identity",
        ),
    )

    provider: RepositoryProvider
    owner: str = Field(min_length=1)
    name: str = Field(min_length=1)
    visibility: RepositoryVisibility
    project: ProjectRef
    default_branch: str | None = None
    source_provenance: SourceProvenance
    public_safety: PublicSafetyClass
    redaction_status: RedactionStatus
