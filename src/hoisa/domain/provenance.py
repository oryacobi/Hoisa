"""Source provenance value objects for normalized Hoisa records."""

from enum import StrEnum

from pydantic import Field

from hoisa.domain.models import HoisaModel, UtcDatetime
from hoisa.domain.privacy import PublicSafetyClass


class SourceSystem(StrEnum):
    """External or internal systems that can originate Hoisa records."""

    HOISA = "hoisa"
    GITHUB = "github"
    HUMAN = "human"
    RUNNER = "runner"
    FILESYSTEM = "filesystem"
    CONVERSATION = "conversation"
    SLACK = "slack"


class ContentHash(HoisaModel):
    """Stable content hash without embedding private content."""

    algorithm: str = Field(min_length=1)
    value: str = Field(min_length=1)


class SourceProvenance(HoisaModel):
    """Attribution for source observations and derived records."""

    source_system: SourceSystem
    source_id: str = Field(min_length=1)
    observed_at: UtcDatetime
    source_url: str | None = None
    external_updated_at: UtcDatetime | None = None
    content_hash: ContentHash | None = None
    public_safety: PublicSafetyClass = PublicSafetyClass.PUBLIC
