"""Shared Pydantic model conventions for Hoisa domain records."""

from datetime import UTC, datetime
from typing import Annotated

from pydantic import AfterValidator, BaseModel, ConfigDict, Field


def normalize_utc_datetime(value: datetime) -> datetime:
    """Require timezone-aware datetimes and normalize them to UTC."""

    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("Datetime values must be timezone-aware.")
    return value.astimezone(UTC)


UtcDatetime = Annotated[datetime, AfterValidator(normalize_utc_datetime)]


class HoisaModel(BaseModel):
    """Base model for Hoisa value objects and boundary records."""

    model_config = ConfigDict(extra="forbid", frozen=True)


class CollectionRoot(HoisaModel):
    """Common fields for current-state records stored as collection roots."""

    created_at: UtcDatetime
    updated_at: UtcDatetime
    schema_version: int = Field(default=1, ge=1)
