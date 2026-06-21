"""Hoisa's thin Antonic connector."""

from collections.abc import Mapping
from typing import Any

from antonic import AntConnector, AntDoc, DuplicateAntDocError, OptimisticLockError

from hoisa.adapters.persistence.core import DURABLE_RECORD_TYPES, HoisaPersistenceHelpers
from hoisa.ports.persistence import DuplicateRecordError, PersistenceConflictError


class HoisaAntConnector(HoisaPersistenceHelpers, AntConnector):
    """Antonic connector preloaded with Hoisa records and error translation."""

    def __init__(
        self,
        connection_string: str | None = None,
        *,
        database: str | None = None,
        client_options: Mapping[str, Any] | None = None,
        strict_registration: bool = False,
    ) -> None:
        super().__init__(
            connection_string,
            database=database,
            client_options=client_options,
            strict_registration=strict_registration,
        )
        self.register(*DURABLE_RECORD_TYPES)

    async def insert[T: AntDoc](
        self,
        ant_doc: T,
        *,
        mongo_options: Mapping[str, Any] | None = None,
    ) -> T:
        try:
            return await super().insert(ant_doc, mongo_options=mongo_options)
        except DuplicateAntDocError as exc:
            raise DuplicateRecordError(str(exc)) from exc

    async def save[T: AntDoc](
        self,
        ant_doc: T,
        *,
        upsert: bool = False,
        mongo_options: Mapping[str, Any] | None = None,
        **where: Any,
    ) -> T:
        try:
            return await super().save(
                ant_doc,
                upsert=upsert,
                mongo_options=mongo_options,
                **where,
            )
        except DuplicateAntDocError as exc:
            raise DuplicateRecordError(str(exc)) from exc
        except OptimisticLockError as exc:
            raise PersistenceConflictError(str(exc)) from exc
