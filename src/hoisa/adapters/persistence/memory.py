"""Generic in-memory Antonic-style store for Hoisa tests."""

from collections.abc import Callable, Mapping, Sequence
from datetime import UTC, datetime
from enum import Enum
from typing import Any, cast

from antonic import AntDoc
from antonic.query import validate_query
from antonic.registry import AntDocMeta, AntDocRegistry
from bson import ObjectId

from hoisa.adapters.persistence.core import DURABLE_RECORD_TYPES, HoisaPersistenceHelpers
from hoisa.ports.persistence import (
    DuplicateRecordError,
    PersistenceConflictError,
    RecordNotFoundError,
)

_MISSING = object()


class InMemoryStore(HoisaPersistenceHelpers):
    """In-memory implementation of Antonic's generic document surface."""

    def __init__(self, *, strict_registration: bool = False) -> None:
        self.registry = AntDocRegistry(strict=strict_registration)
        self._records: dict[type[AntDoc], dict[Any, AntDoc]] = {}
        self.register(*DURABLE_RECORD_TYPES)

    def register(
        self, doc_type: type[AntDoc], *doc_types: type[AntDoc]
    ) -> AntDocMeta | tuple[AntDocMeta, ...]:
        metas = tuple(self.registry.register(item) for item in (doc_type, *doc_types))
        for meta in metas:
            self._records.setdefault(meta.doc_type, {})
        return metas[0] if len(metas) == 1 else metas

    async def close(self) -> None:
        """Mirror Antonic connector close."""

    async def ensure_indexes(
        self,
        *doc_types: type[AntDoc],
        mongo_options: Mapping[str, Any] | None = None,
    ) -> dict[type[AntDoc], list[str]]:
        """Return declared index names; enforcement happens on writes."""

        _ = mongo_options
        targets = doc_types or tuple(self.registry.registered_types())
        return {
            doc_type: [
                index.name for index in self.registry.resolve(doc_type).indexes if index.name
            ]
            for doc_type in targets
        }

    async def insert[T: AntDoc](
        self,
        ant_doc: T,
        *,
        mongo_options: Mapping[str, Any] | None = None,
    ) -> T:
        _ = mongo_options
        meta = self.registry.resolve(type(ant_doc))
        next_doc = self._prepare_insert(meta, ant_doc)
        bucket = self._bucket(meta.doc_type)
        if next_doc.id in bucket:
            raise DuplicateRecordError(f"Document already exists: {next_doc.id}")
        self._reject_unique_collisions(meta, next_doc, current_id=None)
        bucket[next_doc.id] = next_doc
        return next_doc

    async def save[T: AntDoc](
        self,
        ant_doc: T,
        *,
        upsert: bool = False,
        mongo_options: Mapping[str, Any] | None = None,
        **where: Any,
    ) -> T:
        _ = mongo_options
        meta = self.registry.resolve(type(ant_doc))
        if ant_doc.id is None or (meta.optimistic_lock and ant_doc.version == 0):
            return await self.insert(ant_doc, mongo_options=mongo_options)

        record_id = self._record_id(meta, ant_doc.id)
        bucket = self._bucket(meta.doc_type)
        existing = bucket.get(record_id)
        if existing is None:
            if upsert:
                return await self.insert(ant_doc, mongo_options=mongo_options)
            raise RecordNotFoundError(f"{meta.doc_type.__name__} not found: {record_id}")
        if where and not _matches(existing, validate_query(where)):
            raise RecordNotFoundError(f"{meta.doc_type.__name__} did not match save filter")
        if meta.optimistic_lock and existing.version != ant_doc.version:
            raise PersistenceConflictError(meta.doc_type.__name__)

        updates: dict[str, Any] = {"id": record_id}
        if meta.timestamps:
            updates["updated_at"] = datetime.now(UTC)
        if meta.optimistic_lock:
            updates["version"] = ant_doc.version + 1
        next_doc = ant_doc.model_copy(update=updates)
        self._reject_unique_collisions(meta, next_doc, current_id=record_id)
        bucket[record_id] = next_doc
        return next_doc

    async def get[T: AntDoc](
        self,
        doc_type: type[T],
        id: Any = None,
        filter: Mapping[str, Any] | None = None,
        *,
        projection: Any = None,
        sort: Any = None,
        mongo_options: Mapping[str, Any] | None = None,
        **where: Any,
    ) -> T | None:
        _ = projection
        _ = mongo_options
        query = self._query(doc_type, filter, where)
        if id is not None:
            query["id"] = id
        records = await self.find(doc_type, query, sort=sort, limit=1)
        return records[0] if records else None

    async def find[T: AntDoc](
        self,
        doc_type: type[T],
        filter: Mapping[str, Any] | None = None,
        *,
        projection: Any = None,
        sort: Any = None,
        limit: int | None = None,
        skip: int | None = None,
        mongo_options: Mapping[str, Any] | None = None,
        **where: Any,
    ) -> list[T]:
        _ = projection
        _ = mongo_options
        query = self._query(doc_type, filter, where)
        records = [
            cast(T, record)
            for record in self._bucket(self.registry.resolve(doc_type).doc_type).values()
            if _matches(record, query)
        ]
        records = _sort(records, sort)
        if skip is not None:
            records = records[skip:]
        if limit is not None:
            records = records[:limit]
        return records

    def _query(
        self,
        doc_type: type[AntDoc],
        filter: Mapping[str, Any] | None,
        where: Mapping[str, Any],
    ) -> dict[str, Any]:
        self.registry.resolve(doc_type)
        query = dict(filter or {})
        query.update(where)
        return validate_query(query)

    def _prepare_insert[T: AntDoc](self, meta: AntDocMeta, ant_doc: T) -> T:
        now = datetime.now(UTC)
        updates: dict[str, Any] = {"id": self._new_id(meta, ant_doc.id)}
        if meta.timestamps:
            updates["created_at"] = ant_doc.created_at or now
            updates["updated_at"] = now
        if meta.optimistic_lock:
            updates["version"] = 1
        return ant_doc.model_copy(update=updates)

    def _new_id(self, meta: AntDocMeta, value: Any) -> Any:
        if value is None:
            return meta.id_factory() if meta.id_factory is not None else ObjectId()
        return self._record_id(meta, value)

    def _record_id(self, meta: AntDocMeta, value: Any) -> Any:
        if meta.id_type in {None, ObjectId} and isinstance(value, str) and ObjectId.is_valid(value):
            return ObjectId(value)
        return value

    def _bucket(self, doc_type: type[AntDoc]) -> dict[Any, AntDoc]:
        return self._records.setdefault(doc_type, {})

    def _reject_unique_collisions(
        self,
        meta: AntDocMeta,
        record: AntDoc,
        *,
        current_id: Any,
    ) -> None:
        for index in meta.indexes:
            if not index.unique:
                continue
            if index.partial_filter is not None and not _matches(record, index.partial_filter):
                continue

            key = _index_key(record, index.keys)
            if index.sparse and _has_sparse_gap(key):
                continue

            for existing in self._bucket(meta.doc_type).values():
                if current_id is not None and existing.id == current_id:
                    continue
                if index.partial_filter is not None and not _matches(
                    existing, index.partial_filter
                ):
                    continue
                existing_key = _index_key(existing, index.keys)
                if index.sparse and _has_sparse_gap(existing_key):
                    continue
                if existing_key == key:
                    label = index.name or ", ".join(field for field, _direction in index.keys)
                    raise DuplicateRecordError(f"Duplicate {label}: {key}")


def _matches(record: AntDoc, query: Mapping[str, Any]) -> bool:
    for field, expected in query.items():
        if field == "$and":
            if not all(_matches(record, item) for item in expected):
                return False
            continue
        if field == "$or":
            if not any(_matches(record, item) for item in expected):
                return False
            continue

        actual = _field_value(record, field)
        if isinstance(expected, Mapping) and _contains_operator(expected):
            if not _matches_operator(actual, expected):
                return False
            continue
        if not _equal(actual, expected):
            return False
    return True


def _contains_operator(value: Mapping[Any, Any]) -> bool:
    return any(isinstance(key, str) and key.startswith("$") for key in value)


def _matches_operator(actual: Any, operators: Mapping[str, Any]) -> bool:
    for operator, expected in operators.items():
        if operator == "$eq" and not _equal(actual, expected):
            return False
        if operator == "$ne" and _equal(actual, expected):
            return False
        if operator == "$in" and not any(_equal(actual, item) for item in expected):
            return False
        if operator == "$nin" and any(_equal(actual, item) for item in expected):
            return False
        if operator == "$exists" and ((actual is not _MISSING) != expected):
            return False
        if operator == "$gt" and not _compare(actual, expected, lambda left, right: left > right):
            return False
        if operator == "$gte" and not _compare(actual, expected, lambda left, right: left >= right):
            return False
        if operator == "$lt" and not _compare(actual, expected, lambda left, right: left < right):
            return False
        if operator == "$lte" and not _compare(actual, expected, lambda left, right: left <= right):
            return False
    return True


def _compare(actual: Any, expected: Any, op: Callable[[Any, Any], bool]) -> bool:
    if actual is _MISSING:
        return False
    return bool(op(actual, _normalize_expected(actual, expected)))


def _equal(actual: Any, expected: Any) -> bool:
    if actual is _MISSING:
        return False
    return bool(actual == _normalize_expected(actual, expected))


def _normalize_expected(actual: Any, expected: Any) -> Any:
    if isinstance(actual, ObjectId) and isinstance(expected, str) and ObjectId.is_valid(expected):
        return ObjectId(expected)
    if isinstance(actual, Enum) and isinstance(expected, str):
        return actual.value.__class__(expected)
    return expected


def _field_value(record: Any, field: str) -> Any:
    value = record
    for part in field.split("."):
        if value is _MISSING:
            return _MISSING
        if isinstance(value, Mapping):
            value = value.get(part, _MISSING)
            continue
        value = getattr(value, part, _MISSING)
    return value


def _index_key(record: AntDoc, keys: Sequence[tuple[str, Any]]) -> tuple[Any, ...]:
    return tuple(_field_value(record, field) for field, _direction in keys)


def _has_sparse_gap(key: tuple[Any, ...]) -> bool:
    return any(value is _MISSING or value is None for value in key)


def _sort[T](records: list[T], sort: Any) -> list[T]:
    if sort is None:
        return records
    sorted_records = list(records)
    for field, direction in reversed(sort):

        def sort_key(record: T, sort_field: str = field) -> tuple[bool, Any]:
            return _sort_key(_field_value(record, sort_field))

        sorted_records.sort(
            key=sort_key,
            reverse=direction < 0,
        )
    return sorted_records


def _sort_key(value: Any) -> tuple[bool, Any]:
    if value is _MISSING or value is None:
        return (True, "")
    return (False, value)
