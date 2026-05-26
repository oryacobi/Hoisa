"""Source observation records reduced into Hoisa workflow state."""

from enum import StrEnum

from pydantic import Field

from hoisa.domain.models import BsonObjectId, CollectionRoot
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

    source_connection_id: BsonObjectId
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

    source_connection_id: BsonObjectId
    cursor_name: str = Field(min_length=1)
    cursor_value: str = Field(min_length=1)
    source_provenance: SourceProvenance
    public_safety: PublicSafetyClass
    redaction_status: RedactionStatus
