"""Shared Pydantic model conventions for Hoisa domain records."""

from datetime import UTC, datetime
from typing import Annotated, Any

from bson import ObjectId
from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
    GetCoreSchemaHandler,
    GetJsonSchemaHandler,
)
from pydantic.json_schema import JsonSchemaValue
from pydantic_core import core_schema


def normalize_utc_datetime(value: datetime) -> datetime:
    """Require timezone-aware datetimes and normalize them to UTC."""

    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("Datetime values must be timezone-aware.")
    return value.astimezone(UTC)


UtcDatetime = Annotated[datetime, AfterValidator(normalize_utc_datetime)]


def new_object_id() -> ObjectId:
    return ObjectId()


class _BsonObjectIdPydanticAnnotation:
    @classmethod
    def __get_pydantic_core_schema__(
        cls,
        _source_type: Any,
        _handler: GetCoreSchemaHandler,
    ) -> core_schema.CoreSchema:
        def validate_object_id(value: object) -> ObjectId:
            if isinstance(value, ObjectId):
                return value
            if isinstance(value, str) and ObjectId.is_valid(value):
                return ObjectId(value)
            raise ValueError("Invalid ObjectId.")

        def validate_from_str(value: str) -> ObjectId:
            if not ObjectId.is_valid(value):
                raise ValueError("Invalid ObjectId.")
            return ObjectId(value)

        from_str_schema = core_schema.chain_schema(
            [
                core_schema.str_schema(),
                core_schema.no_info_plain_validator_function(validate_from_str),
            ]
        )
        return core_schema.json_or_python_schema(
            json_schema=from_str_schema,
            python_schema=core_schema.no_info_plain_validator_function(
                validate_object_id,
            ),
            serialization=core_schema.plain_serializer_function_ser_schema(
                lambda value: str(value),
                when_used="json",
            ),
        )

    @classmethod
    def __get_pydantic_json_schema__(
        cls,
        _core_schema: core_schema.CoreSchema,
        _handler: GetJsonSchemaHandler,
    ) -> JsonSchemaValue:
        return {
            "pattern": "^[0-9a-fA-F]{24}$",
            "type": "string",
        }


BsonObjectId = Annotated[ObjectId, _BsonObjectIdPydanticAnnotation]


class HoisaModel(BaseModel):
    """Base model for Hoisa value objects and boundary records."""

    model_config = ConfigDict(extra="forbid", frozen=True)


class CollectionRoot(HoisaModel):
    """Common fields for current-state records stored as collection roots."""

    id: BsonObjectId = Field(default_factory=new_object_id)
    created_at: UtcDatetime
    updated_at: UtcDatetime
    schema_version: int = Field(default=1, ge=1)
