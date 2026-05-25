---
issue: 9
title: "[Task]: Add persistence ports and in-memory adapters"
agent: Codex
branch: codex/9-task-add-persistence-ports-and-in-memory-adapter
created: 2026-05-25
superseded_by:
linked_pr:
---

# Plan for #9: [Task]: Add persistence ports and in-memory adapters

## Summary
- Define Hoisa's first persistence port surface around workflow use cases, not
  database collections or generic CRUD.
- Add the small missing domain records needed for those ports: project and
  target-repo collection roots, source observations and sync cursors,
  workflow-state persistence, and tool-control records. Reuse the existing
  work item, gate, run, evidence bundle, task packet, and workflow event models
  from issue #6.
- Implement a deterministic in-memory persistence adapter that satisfies the
  same shared contract tests future durable adapters must pass.
- Keep this as a local, testable ports-and-adapters slice. No MongoDB, GitHub,
  filesystem, runner, migration framework, or external write behavior belongs
  in this issue.

## Decision
- Use typed Python `Protocol` ports in `src/hoisa/ports/persistence.py`, backed
  by Pydantic domain records and small frozen query value objects.
- Prefer async repository methods for persistence ports so future MongoDB
  adapters can sit behind the same interface without adding a second contract.
  Tests can exercise async methods with `asyncio.run` rather than adding a new
  pytest dependency.
- Expose a repository/provider surface with intention-revealing methods:
  - save and get by stable Hoisa IDs;
  - list or find by project/repo/workflow keys where the application needs that
    query;
  - runnable-work queries;
  - waiting-gate queries;
  - workflow lease/state lookups;
  - source observation and sync cursor upserts;
  - event listing by subject and correlation.
- Do not expose collection names, MongoDB `_id`, PyMongo/Motor types, raw
  driver errors, or generic database operations through ports or application
  code.
- Treat collection-root records as immutable snapshots with `created_at`,
  `updated_at`, and `schema_version`. Adapters may replace saved snapshots, but
  callers should not mutate records in place.
- Keep duplicate-key and missing-record behavior explicit with port-level
  exceptions or return types, rather than leaking adapter-specific exceptions.

## Implementation Approach
- Expand or add domain modules only where persistence coverage needs a typed
  record that does not exist yet:
  - `src/hoisa/domain/target_repos.py`: add collection-root `Project` and
    `TargetRepo` records while preserving existing `ProjectRef` and
    `TargetRepoRef` value objects used by current models.
  - `src/hoisa/domain/sources.py` or an equivalently named module:
    `SourceConnection`, `SourceObservation`, and `SyncCursor` records with
    source IDs, external IDs, content hashes/cursor values, provenance,
    public-safety classification, and redaction status. Store compact summaries
    or schema-named payloads only; do not embed raw private source content.
  - `src/hoisa/domain/workflow_state.py`: add a collection-root
    `WorkflowStateRecord` or similarly narrow wrapper that persists the
    existing `WorkflowState` value object by `work_item_id` without duplicating
    broader work-item fields.
  - `src/hoisa/domain/tool_control.py`: add minimal records for
    `ToolConnection`, `ToolPolicy`, `ActionRequest`, and `ToolInvocation`.
    These records should describe requests, status, required gates, summaries,
    evidence, and provenance; they must not execute or authorize tool actions.
- Fill `src/hoisa/ports/persistence.py` with:
  - query/value objects such as `RunnableWorkQuery`, `WaitingGateQuery`,
    `LeaseLookupQuery`, `EventQuery`, `SourceObservationQuery`, and cursor/key
    objects where they keep call sites clear;
  - repository protocols for projects, target repos, source observations,
    sync cursors, work items, workflow state, gates, runs, evidence bundles,
    tool-control records, and workflow events;
  - a provider protocol, such as `PersistenceProvider`, that exposes the typed
    repositories and `WorkflowEventStore` as properties;
  - small adapter-neutral exceptions for duplicate records, stale/missing
    records, or invalid persistence operations when return values are not
    expressive enough.
- Implement `src/hoisa/adapters/persistence/memory.py`:
  - an in-memory provider class that implements every persistence repository
    protocol;
  - deterministic dictionaries/lists keyed by stable Hoisa IDs and secondary
    indexes needed by the contract tests;
  - append-only workflow event behavior, preserving insertion order but
    returning query results in deterministic timestamp/ID order;
  - explicit duplicate-key checks for stable unique identities such as
    `project_id`, `target_repo_id`, repo provider/owner/name,
    `source_connection_id`, source observation source/external/hash,
    sync cursor source/name, `work_item_id`, tracker issue refs, `gate_id`,
    `run_id`, `bundle_id`, tool-control IDs, and `event_id`;
  - deterministic clock handling by accepting fully formed records from tests
    and callers, rather than silently stamping wall-clock time inside the
    adapter.
- Do not wire the memory adapter into a service loop or CLI command in this
  issue. It should be directly importable for tests and later application
  workflows.
- Preserve the architecture contract:
  - domain imports no ports or adapters;
  - ports import domain records but no adapters, service, CLI, PyMongo/Motor,
    GitHub clients, or filesystem/runtime APIs;
  - the memory adapter may import domain and ports only.

## Interfaces
- Python port interface:
  - `hoisa.ports.persistence.PersistenceProvider`
  - `ProjectRepository`
  - `TargetRepoRepository`
  - `SourceObservationRepository`
  - `SyncCursorRepository`
  - `WorkItemRepository`
  - `WorkflowStateRepository`
  - `ApprovalGateRepository`
  - `AgentRunRepository`
  - `EvidenceBundleRepository`
  - `ToolControlRepository` or split tool-control repositories if one protocol
    becomes too broad
  - `WorkflowEventStore`
- Key repository methods should include, at minimum:
  - project/repo save/get/list-by-project and repo lookup by provider/owner/name;
  - work item save/get/find by tracker issue and `find_runnable(query)`;
  - workflow state save/get and lease lookups by worker, active lease, and
    expiration;
  - gate save/get, waiting gate queries by work item or tracker issue, and
    decision persistence if represented as a full gate replacement;
  - run/evidence/tool-control save/get/list methods needed by workflow history
    and review surfaces;
  - event `append`, `list_for_subject`, `list_for_correlation`, and optionally
    bounded `list_recent`.
- Adapter interface:
  - `hoisa.adapters.persistence.memory.InMemoryPersistenceProvider` or an
    equivalent clearly named provider that implements `PersistenceProvider`.
- Test interface:
  - shared contracts live under `tests/contract/persistence/`;
  - the memory adapter is the first implementation bound to those contracts;
  - future MongoDB tests should be able to reuse the same contract helpers or
    pytest fixture shape without rewriting expected behavior.

## Test Plan
- Focused domain tests:
  - new collection-root records carry stable IDs, timezone-aware timestamps, and
    `schema_version`;
  - new source/tool-control records reject missing required IDs and keep private
    content out of public-safe summary fields;
  - workflow-state persistence wrappers preserve lease and blocker data without
    duplicating unrelated work-item state.
- Shared persistence contract tests under `tests/contract/persistence/`:
  - every repository can save and fetch by stable ID;
  - duplicate stable IDs and declared unique composite keys are rejected
    deterministically;
  - runnable-work queries return only eligible work for status, workflow stage,
    risk/project/repo filters where present, and lease expiration rules;
  - waiting-gate queries return only waiting gates, ordered deterministically;
  - lease lookups identify active, expired, and worker-owned leases;
  - source observations and sync cursors upsert/list by source connection and
    cursor names without raw source content;
  - tool-control records can be saved, queried by status/gate/tool type, and
    linked to evidence without invoking tools;
  - workflow events are append-only, reject duplicate event IDs, and list by
    subject and correlation in deterministic order;
  - all persisted collection roots preserve or validate `schema_version`.
- Memory adapter tests:
  - bind the shared contract suite to `InMemoryPersistenceProvider`;
  - prove instances do not share state across tests;
  - prove query results are deterministic even when records are inserted in a
    different order.
- Architecture regression tests:
  - extend existing import-boundary tests only if new modules require explicit
    coverage;
  - verify no PyMongo/Motor, GitHub client, filesystem adapter, service, or CLI
    dependency enters domain or port modules.
- Required checks before PR:
  - `uv run python -m py_compile scripts/github/agent_workflow.py`
  - `uv run ruff check .`
  - `uv run ruff format --check .`
  - `uv run mypy scripts src tests`
  - `uv run pytest`
- Acceptance mapping:
  - port coverage is proven by protocols and contract tests exercising each
    repository surface named in the issue;
  - intention-revealing APIs are proven by tests calling runnable-work,
    waiting-gate, lease, subject, and correlation queries directly;
  - memory determinism is proven by repeated contract tests and ordering tests;
  - no generic CRUD or collection-name leakage is covered by architecture and
    contract tests plus code review.

## Risks
- Risk level: treat as high for workflow purposes. The issue label is
  `risk:medium`, but the helper classified issue quality as high risk because
  persistence contracts will shape workflow-helper and future service behavior.
- Review route: `Review Both`. This plan should receive independent plan
  review before human implementation approval, and the implementation PR should
  receive independent review before the issue is considered implemented.
- Source-of-truth risk: medium-high. Mitigate by making workflow-state,
  runnable-work, gate, lease, and event queries explicit in ports rather than
  inferring them from adapter internals.
- Public/private leakage risk: medium. Mitigate with public-safe summaries,
  provenance and redaction fields, no raw logs/source payloads in fixtures, and
  no local paths or private target-repo content in this public repository.
- Overbuilding risk: medium. Mitigate by adding only the records and queries
  needed for issue acceptance and future MongoDB contracts. Do not add a
  service loop, CLI, migrations, source reducers, action policy engine, or
  durable adapter.
- Adapter-coupling risk: medium. Mitigate with Protocols, in-memory contracts,
  no driver types in ports/domain, and no database collection names outside
  adapter internals or architecture documentation.
- Async complexity risk: low-medium. Mitigate by keeping async repository
  methods simple and testing them with standard-library `asyncio.run`.
- Approval gate: human approval authorizes only the port, domain-record,
  in-memory-adapter, and contract-test slice described here. It does not
  authorize MongoDB, external writes, GitHub/project mutations, runner
  execution, secrets handling, private database contents, or scope expansion.

## Simplification Check
- This issue should create reusable contracts before durability. That reduces
  future MongoDB risk because adapter behavior is specified once and exercised
  by both memory and durable implementations.
- Do not build a generic repository framework. Separate protocols may share
  small query/key value objects, but behavior should stay named by Hoisa use
  case.
- Do not create a migration system. The only versioning expectation in this
  slice is that persisted collection roots and events carry `schema_version`
  and contract tests assert it is present.
- Do not create public JSON schemas for every new internal persistence record
  unless implementation discovers an existing public-schema contract that would
  otherwise break. The issue acceptance is about Python ports and adapter
  contracts, not external schema publication.
- Reuse existing Pydantic base models and workflow vocabulary from issue #6
  rather than introducing a second model stack.

## Assumptions
- The implementation may add small domain records beyond those from issue #6
  when they are necessary to make the persistence port complete.
- Async repository ports are acceptable for the first persistence contract even
  though the existing tracker `WorkQueue` port is synchronous.
- The in-memory adapter is a test and local-development adapter only. It is not
  durable and should not be presented as a replacement for MongoDB.
- Contract tests may use fake public-safe records and synthetic IDs. They must
  not include real target-repo content, secrets, local paths, raw logs, or
  private business data.

## Out Of Scope
- MongoDB, PyMongo, Motor, indexes against a live database, transactions, or
  connection management.
- Filesystem, GitHub, tracker, source-sync, runner, or notification adapters.
- Workflow service loop integration, CLI commands, background workers, or
  dashboard/voice surfaces.
- Migration framework, destructive migrations, backup/retention policy, or
  local database credential handling.
- External tool execution, external write authorization, or policy evaluation
  beyond storing tool-control records.
- Public/private export pipelines or redaction engines beyond fields and tests
  needed for these records.

## Revision History
- 2026-05-25: Initial plan scaffold.
- 2026-05-25: Filled implementation-ready plan for persistence ports,
  in-memory adapter, and shared contract tests.
