import asyncio
from collections.abc import Coroutine
from typing import Any

from hoisa.adapters.persistence.memory import InMemoryPersistenceProvider

from .provider_contract import (
    assert_events_are_append_only_and_query_order_is_deterministic,
    assert_repositories_save_and_fetch_current_state_records,
    assert_runnable_gate_and_lease_queries_are_intention_revealing,
    assert_unique_keys_are_rejected_deterministically,
    project,
)


def test_repositories_save_and_fetch_current_state_records() -> None:
    provider = InMemoryPersistenceProvider()

    run(assert_repositories_save_and_fetch_current_state_records(provider))


def test_unique_keys_are_rejected_deterministically() -> None:
    provider = InMemoryPersistenceProvider()

    run(assert_unique_keys_are_rejected_deterministically(provider))


def test_runnable_gate_and_lease_queries_are_intention_revealing() -> None:
    provider = InMemoryPersistenceProvider()

    run(assert_runnable_gate_and_lease_queries_are_intention_revealing(provider))


def test_events_are_append_only_and_query_order_is_deterministic() -> None:
    provider = InMemoryPersistenceProvider()

    run(assert_events_are_append_only_and_query_order_is_deterministic(provider))


def test_provider_instances_do_not_share_state() -> None:
    first = InMemoryPersistenceProvider()
    second = InMemoryPersistenceProvider()
    run(first.projects.save(project()))

    assert len(run(first.projects.list_all())) == 1
    assert len(run(second.projects.list_all())) == 0


def run[T](coro: Coroutine[Any, Any, T]) -> T:
    return asyncio.run(coro)
