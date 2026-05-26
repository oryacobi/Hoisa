import asyncio
from collections.abc import Awaitable, Callable, Coroutine
from inspect import isawaitable
import os
from typing import Any, cast
import uuid

from pymongo import AsyncMongoClient
from pymongo.errors import ServerSelectionTimeoutError
import pytest

from hoisa.adapters.persistence.mongodb import (
    MONGO_COLLECTION_SPECS,
    MongoCollectionSpec,
    MongoIndexSpec,
    MongoPersistenceProvider,
)
from hoisa.ports.persistence import PersistenceError

from .provider_contract import (
    assert_events_are_append_only_and_query_order_is_deterministic,
    assert_repositories_save_and_fetch_current_state_records,
    assert_round_tripped_datetimes_are_timezone_aware,
    assert_runnable_gate_and_lease_queries_are_intention_revealing,
    assert_unique_keys_are_rejected_deterministically,
    object_id,
    project,
)

TEST_DATABASE_PREFIX = "hoisa_test_"


def test_mongodb_collection_mapping_is_explicit() -> None:
    specs = {spec.collection_name: spec for spec in MONGO_COLLECTION_SPECS}

    assert set(specs) == {
        "projects",
        "target_repos",
        "source_connections",
        "source_observations",
        "sync_cursors",
        "work_items",
        "workflow_states",
        "approval_gates",
        "agent_runs",
        "evidence_bundles",
        "tool_connections",
        "tool_policies",
        "action_requests",
        "tool_invocations",
        "workflow_events",
    }
    assert specs["projects"].model_type.__name__ == "Project"
    assert specs["workflow_events"].model_type.__name__ == "WorkflowEvent"


def test_mongodb_package_exports_provider() -> None:
    from hoisa.adapters.persistence import mongodb

    assert mongodb.MongoPersistenceProvider is MongoPersistenceProvider


def test_mongodb_index_specs_include_unique_and_query_indexes() -> None:
    specs = {spec.collection_name: spec for spec in MONGO_COLLECTION_SPECS}

    assert_unique_index(specs["target_repos"], "provider_owner_name_unique")
    assert_unique_index(specs["source_observations"], "source_external_hash_unique")
    assert_unique_index(specs["sync_cursors"], "source_cursor_unique")
    assert_unique_index(specs["work_items"], "tracker_issue_unique")
    assert_unique_index(specs["tool_policies"], "project_tool_action_unique")
    assert_query_index(specs["workflow_states"], "lease_worker_expiration_lookup")
    assert_query_index(specs["approval_gates"], "status_created_lookup")
    assert_query_index(specs["tool_invocations"], "tool_action_status_happened_lookup")
    assert_query_index(specs["workflow_events"], "subject_happened_lookup")
    assert_query_index(specs["workflow_events"], "correlation_happened_lookup")


def test_repositories_save_and_fetch_current_state_records() -> None:
    run_mongo_contract(assert_repositories_save_and_fetch_current_state_records)


def test_unique_keys_are_rejected_deterministically() -> None:
    run_mongo_contract(assert_unique_keys_are_rejected_deterministically)


def test_runnable_gate_and_lease_queries_are_intention_revealing() -> None:
    run_mongo_contract(assert_runnable_gate_and_lease_queries_are_intention_revealing)


def test_events_are_append_only_and_query_order_is_deterministic() -> None:
    run_mongo_contract(assert_events_are_append_only_and_query_order_is_deterministic)


def test_round_tripped_datetimes_are_timezone_aware() -> None:
    run_mongo_contract(assert_round_tripped_datetimes_are_timezone_aware)


def test_mongodb_uses_bson_id_without_duplicate_root_id() -> None:
    run_mongo_contract(assert_mongodb_stores_bson_id_without_root_id)


def assert_unique_index(spec: MongoCollectionSpec[Any], name: str) -> None:
    index = index_by_name(spec, name)

    assert index.unique


def assert_query_index(spec: MongoCollectionSpec[Any], name: str) -> None:
    index = index_by_name(spec, name)

    assert index.keys


def index_by_name(spec: MongoCollectionSpec[Any], name: str) -> MongoIndexSpec:
    for index in spec.indexes:
        if index.name == name:
            return index
    raise AssertionError(f"Missing MongoDB index spec {name} on {spec.collection_name}")


async def assert_mongodb_stores_bson_id_without_root_id(
    provider: MongoPersistenceProvider,
) -> None:
    await provider.catalog.save_project(project())

    document = await provider.adapter._database.get_collection("projects").find_one(
        {"_id": object_id("project-sample")}
    )

    assert document is not None
    assert document["_id"] == object_id("project-sample")
    assert "id" not in document


def run_mongo_contract(
    assertion: Callable[[MongoPersistenceProvider], Awaitable[None]],
) -> None:
    run(with_mongo_provider(assertion))


async def with_mongo_provider(
    assertion: Callable[[MongoPersistenceProvider], Awaitable[None]],
) -> None:
    uri, database_name = mongo_test_config_or_skip()
    client: AsyncMongoClient[dict[str, Any]] = AsyncMongoClient(
        uri,
        serverSelectionTimeoutMS=2000,
    )
    provider = MongoPersistenceProvider(client, database_name=database_name)
    indexes_ready = False
    try:
        try:
            await provider.ensure_indexes()
        except PersistenceError as exc:
            if isinstance(exc.__cause__, ServerSelectionTimeoutError):
                pytest.skip("MongoDB test service is unavailable.")
            raise
        indexes_ready = True
        await assertion(provider)
    finally:
        if indexes_ready:
            await maybe_await(client.drop_database(database_name))
        await provider.close()


def mongo_test_config_or_skip() -> tuple[str, str]:
    uri = os.environ.get("HOISA_MONGO_TEST_URI")
    database_prefix = os.environ.get("HOISA_MONGO_TEST_DATABASE")
    if not uri or not database_prefix:
        pytest.skip(
            "Set HOISA_MONGO_TEST_URI and HOISA_MONGO_TEST_DATABASE to run MongoDB contracts."
        )
    if not database_prefix.startswith(TEST_DATABASE_PREFIX):
        raise AssertionError(f"HOISA_MONGO_TEST_DATABASE must start with {TEST_DATABASE_PREFIX!r}.")
    return uri, f"{database_prefix}{uuid.uuid4().hex}"


async def maybe_await(value: object) -> None:
    if isawaitable(value):
        await cast(Awaitable[None], value)


def run[T](coro: Coroutine[Any, Any, T]) -> T:
    return asyncio.run(coro)
