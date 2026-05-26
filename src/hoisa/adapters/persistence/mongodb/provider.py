"""MongoDB persistence provider wiring."""

from typing import Self

from pymongo import AsyncMongoClient

from hoisa.adapters.persistence.mongodb.adapter import MongoAdapter
from hoisa.adapters.persistence.mongodb.collections import Document
from hoisa.adapters.persistence.mongodb.gateways import (
    MongoCatalogGateway,
    MongoEventGateway,
    MongoEvidenceGateway,
    MongoSourceGateway,
    MongoToolGateway,
    MongoWorkflowGateway,
)
from hoisa.ports.persistence import (
    CatalogGateway,
    EventGateway,
    EvidenceGateway,
    PersistenceProvider,
    SourceGateway,
    ToolGateway,
    WorkflowGateway,
)


class MongoPersistenceProvider(PersistenceProvider):
    """MongoDB implementation of Hoisa persistence gateways."""

    def __init__(
        self,
        client: AsyncMongoClient[Document],
        *,
        database_name: str,
    ) -> None:
        self.adapter = MongoAdapter(client, database_name=database_name)
        self.database_name = database_name
        self._catalog = MongoCatalogGateway(self.adapter)
        self._sources = MongoSourceGateway(self.adapter)
        self._workflow = MongoWorkflowGateway(self.adapter)
        self._evidence = MongoEvidenceGateway(self.adapter)
        self._tools = MongoToolGateway(self.adapter)
        self._events = MongoEventGateway(self.adapter)

    @classmethod
    def from_uri(
        cls,
        uri: str,
        *,
        database_name: str,
        server_selection_timeout_ms: int = 2000,
    ) -> Self:
        """Create a provider from a MongoDB URI without exposing it through ports."""

        client: AsyncMongoClient[Document] = AsyncMongoClient(
            uri,
            serverSelectionTimeoutMS=server_selection_timeout_ms,
        )
        return cls(client, database_name=database_name)

    async def ensure_indexes(self) -> None:
        """Create all adapter-owned MongoDB indexes."""

        await self.adapter.ensure_indexes()

    async def close(self) -> None:
        """Close the underlying MongoDB client."""

        await self.adapter.close()

    @property
    def catalog(self) -> CatalogGateway:
        """Return the project and target-repo gateway."""

        return self._catalog

    @property
    def sources(self) -> SourceGateway:
        """Return the source data gateway."""

        return self._sources

    @property
    def workflow(self) -> WorkflowGateway:
        """Return the workflow state gateway."""

        return self._workflow

    @property
    def evidence(self) -> EvidenceGateway:
        """Return the evidence gateway."""

        return self._evidence

    @property
    def tools(self) -> ToolGateway:
        """Return the tool-control gateway."""

        return self._tools

    @property
    def events(self) -> EventGateway:
        """Return the workflow event gateway."""

        return self._events
