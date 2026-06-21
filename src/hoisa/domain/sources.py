"""Source observation records reduced into Hoisa workflow state."""

from enum import StrEnum
from typing import ClassVar

from antonic import AntIndex
from pydantic import Field

from hoisa.domain.models import ASCENDING, CollectionRoot
from hoisa.domain.privacy import PublicSafetyClass, RedactionStatus
from hoisa.domain.provenance import ContentHash, SourceProvenance, SourceSystem
from hoisa.domain.target_repos import ProjectRef, TargetRepoRef

ObservationScalar = str | int | float | bool | None


class SourceConnectionStatus(StrEnum):
    """Lifecycle status for an external source connection."""

    ACTIVE = "active"
    PAUSED = "paused"
    ARCHIVED = "archived"


class SourceConnection(CollectionRoot):
    """Configured source Hoisa observes before reducing records."""

    ant_collection: ClassVar[str] = "source_connections"

    project: ProjectRef
    source_system: SourceSystem
    display_name: str = Field(min_length=1)
    status: SourceConnectionStatus
    target_repo: TargetRepoRef | None = None
    source_provenance: SourceProvenance
    public_safety: PublicSafetyClass
    redaction_status: RedactionStatus


class SourceObservation(CollectionRoot):
    """Public-safe summary of an external source observation."""

    ant_collection: ClassVar[str] = "source_observations"
    ant_indexes: ClassVar[tuple[AntIndex, ...]] = (
        AntIndex(
            [
                ("source_connection_id", ASCENDING),
                ("external_id", ASCENDING),
                ("content_hash.value", ASCENDING),
            ],
            unique=True,
            name="uniq_source_observation_identity",
        ),
    )

    source_connection_id: str = Field(min_length=1)
    external_id: str = Field(min_length=1)
    content_hash: ContentHash
    summary: str = Field(min_length=1)
    payload_schema: str = Field(min_length=1)
    payload: dict[str, ObservationScalar] = Field(default_factory=dict)
    source_provenance: SourceProvenance
    public_safety: PublicSafetyClass
    redaction_status: RedactionStatus


class SyncCursor(CollectionRoot):
    """Cursor for deterministic incremental source observation."""

    ant_collection: ClassVar[str] = "sync_cursors"
    ant_indexes: ClassVar[tuple[AntIndex, ...]] = (
        AntIndex(
            [("source_connection_id", ASCENDING), ("cursor_name", ASCENDING)],
            unique=True,
            name="uniq_sync_cursor_identity",
        ),
    )

    source_connection_id: str = Field(min_length=1)
    cursor_name: str = Field(min_length=1)
    cursor_value: str = Field(min_length=1)
    source_provenance: SourceProvenance
    public_safety: PublicSafetyClass
    redaction_status: RedactionStatus
