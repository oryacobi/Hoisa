"""MongoDB persistence adapter public exports."""

from hoisa.adapters.persistence.mongodb.adapter import MongoAdapter
from hoisa.adapters.persistence.mongodb.collections import (
    MONGO_COLLECTION_SPECS,
    MongoCollectionSpec,
    MongoIndexSpec,
)
from hoisa.adapters.persistence.mongodb.provider import MongoPersistenceProvider

__all__ = [
    "MONGO_COLLECTION_SPECS",
    "MongoAdapter",
    "MongoCollectionSpec",
    "MongoIndexSpec",
    "MongoPersistenceProvider",
]
