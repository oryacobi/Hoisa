"""Type-directed MongoDB document mapper."""

from collections.abc import AsyncIterator, Awaitable, Callable, Mapping, Sequence
from datetime import UTC, datetime
from enum import Enum
from inspect import isawaitable
from typing import Any, cast

from bson.codec_options import CodecOptions
from pydantic import BaseModel
from pymongo import AsyncMongoClient, IndexModel
from pymongo.errors import DuplicateKeyError, PyMongoError

from hoisa.adapters.persistence.mongodb.collections import (
    MONGO_COLLECTION_SPECS,
    Document,
    Filter,
    Hint,
    MongoCollectionSpec,
    MongoIndexSpec,
    SortKey,
)
from hoisa.domain.models import BsonObjectId, CollectionRoot
from hoisa.ports.persistence import (
    DuplicateRecordError,
    PersistenceError,
    RecordNotFoundError,
)


class MongoAdapter:
    """Type-directed MongoDB mapper for Hoisa domain records."""

    def __init__(
        self,
        client: AsyncMongoClient[Document],
        *,
        database_name: str,
        collection_specs: Sequence[MongoCollectionSpec[Any]] = MONGO_COLLECTION_SPECS,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        codec_options: CodecOptions[Document] = CodecOptions(tz_aware=True, tzinfo=UTC)
        self._client = client
        self._database = client.get_database(database_name, codec_options=codec_options)
        self._clock = clock or (lambda: datetime.now(UTC))
        self._specs_by_model = {spec.model_type: spec for spec in collection_specs}

    async def find_one[T: BaseModel](
        self,
        model_type: type[T],
        *,
        id: BsonObjectId | None = None,
        query: Filter | None = None,
        sort: Sequence[SortKey] | None = None,
        hint: Hint | None = None,
    ) -> T | None:
        spec = self._spec_for(model_type)
        try:
            document = await self._collection(spec).find_one(
                self._query(id=id, query=query),
                sort=list(sort) if sort is not None else None,
                hint=hint,
            )
        except PyMongoError as exc:
            raise PersistenceError(f"Failed to read {spec.duplicate_label}.") from exc
        if document is None:
            return None
        return self._entity_from_document(model_type, cast(Mapping[str, Any], document))

    async def find[T: BaseModel](
        self,
        model_type: type[T],
        *,
        query: Filter | None = None,
        sort: Sequence[SortKey] | None = None,
        hint: Hint | None = None,
        limit: int | None = None,
    ) -> AsyncIterator[T]:
        spec = self._spec_for(model_type)
        try:
            cursor = self._collection(spec).find(
                self._query(query=query),
                sort=list(sort) if sort is not None else None,
                hint=hint,
            )
            if limit is not None:
                cursor = cursor.limit(limit)
            async for document in cursor:
                yield self._entity_from_document(model_type, cast(Mapping[str, Any], document))
        except PyMongoError as exc:
            raise PersistenceError(f"Failed to list {spec.duplicate_label}.") from exc

    async def find_many[T: BaseModel](
        self,
        model_type: type[T],
        *,
        query: Filter | None = None,
        sort: Sequence[SortKey] | None = None,
        hint: Hint | None = None,
        limit: int | None = None,
    ) -> tuple[T, ...]:
        return tuple(
            [
                entity
                async for entity in self.find(
                    model_type,
                    query=query,
                    sort=sort,
                    hint=hint,
                    limit=limit,
                )
            ]
        )

    async def insert_entity[T: BaseModel](self, entity: T) -> None:
        spec = self._spec_for(type(entity))
        try:
            await self._collection(spec).insert_one(self._document_for_entity(entity))
        except DuplicateKeyError as exc:
            raise DuplicateRecordError(f"{spec.duplicate_label} already exists.") from exc
        except PyMongoError as exc:
            raise PersistenceError(f"Failed to insert {spec.duplicate_label}.") from exc

    async def update_entity[T: BaseModel](self, entity: T) -> None:
        spec = self._spec_for(type(entity))
        document = self._document_for_entity(self._touch_updated_at(entity))
        try:
            result = await self._collection(spec).replace_one(
                {"_id": document["_id"]},
                document,
                upsert=False,
            )
        except DuplicateKeyError as exc:
            raise DuplicateRecordError(f"Duplicate {spec.duplicate_label}.") from exc
        except PyMongoError as exc:
            raise PersistenceError(f"Failed to update {spec.duplicate_label}.") from exc
        if result.matched_count == 0:
            raise RecordNotFoundError(f"{spec.duplicate_label} does not exist.")

    async def upsert_entity[T: BaseModel](self, entity: T) -> None:
        spec = self._spec_for(type(entity))
        document = self._document_for_entity(self._touch_updated_at(entity))
        try:
            await self._collection(spec).replace_one(
                {"_id": document["_id"]},
                document,
                upsert=True,
            )
        except DuplicateKeyError as exc:
            raise DuplicateRecordError(f"Duplicate {spec.duplicate_label}.") from exc
        except PyMongoError as exc:
            raise PersistenceError(f"Failed to save {spec.duplicate_label}.") from exc

    async def ensure_indexes(self) -> None:
        try:
            for spec in self._specs_by_model.values():
                models = [self._index_model(index) for index in spec.indexes]
                if models:
                    await self._collection(spec).create_indexes(models)
        except PyMongoError as exc:
            raise PersistenceError("Failed to ensure MongoDB persistence indexes.") from exc

    async def close(self) -> None:
        result = self._client.close()
        if isawaitable(result):
            await cast(Awaitable[None], result)

    def _spec_for[T: BaseModel](self, model_type: type[T]) -> MongoCollectionSpec[T]:
        try:
            return cast(MongoCollectionSpec[T], self._specs_by_model[model_type])
        except KeyError as exc:
            raise PersistenceError(f"No MongoDB collection registered for {model_type}.") from exc

    def _collection(self, spec: MongoCollectionSpec[Any]) -> Any:
        return self._database.get_collection(spec.collection_name)

    def _query(
        self,
        *,
        id: BsonObjectId | None = None,
        query: Filter | None = None,
    ) -> Document:
        filter_query = dict(query or {})
        if id is not None:
            filter_query["_id"] = id
        return cast(Document, self._to_bson_value(filter_query))

    def _document_for_entity(self, entity: BaseModel) -> Document:
        data = cast(Document, self._to_bson_value(entity.model_dump(mode="python")))
        document_id = data.pop("id")
        return {"_id": document_id, **data}

    def _entity_from_document[T: BaseModel](
        self,
        model_type: type[T],
        document: Mapping[str, Any],
    ) -> T:
        data = dict(document)
        data["id"] = data.pop("_id")
        return model_type.model_validate(self._ensure_utc_datetimes(data))

    def _touch_updated_at[T: BaseModel](self, entity: T) -> T:
        if isinstance(entity, CollectionRoot):
            return cast(T, entity.model_copy(update={"updated_at": self._clock()}))
        return entity

    def _index_model(self, index_spec: MongoIndexSpec) -> IndexModel:
        kwargs: dict[str, Any] = {
            "name": index_spec.name,
            "unique": index_spec.unique,
        }
        if index_spec.partial_filter_expression is not None:
            kwargs["partialFilterExpression"] = dict(index_spec.partial_filter_expression)
        return IndexModel(list(index_spec.keys), **kwargs)

    def _to_bson_value(self, value: object) -> object:
        if isinstance(value, datetime):
            return value.astimezone(UTC)
        if isinstance(value, Enum):
            return value.value
        if isinstance(value, Mapping):
            return {str(key): self._to_bson_value(nested) for key, nested in value.items()}
        if isinstance(value, tuple | list):
            return [self._to_bson_value(nested) for nested in value]
        return value

    def _ensure_utc_datetimes(self, value: object) -> object:
        if isinstance(value, datetime):
            if value.tzinfo is None or value.utcoffset() is None:
                return value.replace(tzinfo=UTC)
            return value.astimezone(UTC)
        if isinstance(value, Mapping):
            return {str(key): self._ensure_utc_datetimes(nested) for key, nested in value.items()}
        if isinstance(value, list):
            return [self._ensure_utc_datetimes(nested) for nested in value]
        return value
