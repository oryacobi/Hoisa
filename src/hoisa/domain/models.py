"""Shared model conventions for Hoisa domain records."""

from datetime import UTC, datetime
from typing import Annotated, Any

from bson import ObjectId
from pydantic import (
    AfterValidator,
    BaseModel,
    BeforeValidator,
    ConfigDict,
    PlainSerializer,
    WithJsonSchema,
)

ASCENDING = 1
DESCENDING = -1


def normalize_utc_datetime(value: datetime) -> datetime:
    """Require timezone-aware datetimes and normalize them to UTC."""

    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("Datetime values must be timezone-aware.")
    return value.astimezone(UTC)


UtcDatetime = Annotated[datetime, AfterValidator(normalize_utc_datetime)]


def parse_record_id(value: Any) -> ObjectId:
    """Parse public JSON ID strings into Mongo ObjectIds."""

    if isinstance(value, ObjectId):
        return value
    if isinstance(value, str) and ObjectId.is_valid(value):
        return ObjectId(value)
    raise ValueError("Expected a Mongo ObjectId or 24-character ObjectId string.")


RecordId = Annotated[
    ObjectId,
    BeforeValidator(parse_record_id),
    PlainSerializer(str, return_type=str, when_used="json"),
    WithJsonSchema({"type": "string", "pattern": "^[0-9a-fA-F]{24}$"}),
]


class HoisaModel(BaseModel):
    """Base model for embedded Hoisa value objects."""

    model_config = ConfigDict(arbitrary_types_allowed=True, extra="forbid", frozen=True)
