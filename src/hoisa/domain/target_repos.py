"""Project and repository references used by Hoisa records."""

from enum import StrEnum

from pydantic import Field

from hoisa.domain.models import HoisaModel


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


class TargetRepoRef(HoisaModel):
    """Generic repository reference without local paths or access details."""

    target_repo_id: str = Field(min_length=1)
    provider: RepositoryProvider
    owner: str = Field(min_length=1)
    name: str = Field(min_length=1)
    visibility: RepositoryVisibility
    project: ProjectRef
