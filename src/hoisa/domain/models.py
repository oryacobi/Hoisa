"""Shared model conventions for Hoisa domain records."""

from datetime import UTC, datetime
from typing import Annotated, ClassVar

from antonic import AntDoc
from pydantic import AfterValidator, BaseModel, ConfigDict, Field

ASCENDING = 1
DESCENDING = -1


def normalize_utc_datetime(value: datetime) -> datetime:
    """Require timezone-aware datetimes and normalize them to UTC."""

    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("Datetime values must be timezone-aware.")
    return value.astimezone(UTC)


UtcDatetime = Annotated[datetime, AfterValidator(normalize_utc_datetime)]


class HoisaModel(BaseModel):
    """Base model for embedded Hoisa value objects."""

    model_config = ConfigDict(extra="forbid", frozen=True)


class CollectionRoot(AntDoc):
    """Antonic-backed base for durable Hoisa records."""

    id: str = Field(min_length=1)
    created_at: UtcDatetime | None = None
    updated_at: UtcDatetime | None = None
    schema_version: int = Field(default=1, ge=1)

    ant_id_type: ClassVar[type[str]] = str
