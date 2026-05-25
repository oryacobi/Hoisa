---
issue: 11
title: "[Task]: Implement MongoDB persistence adapter"
agent: Codex
branch: codex/11-task-implement-mongodb-persistence-adapter
created: 2026-05-25
superseded_by:
linked_pr:
---

# Plan for #11: [Task]: Implement MongoDB persistence adapter

## Summary
- Add Hoisa's first durable persistence adapter behind the existing
  `hoisa.ports.persistence` repository and event-store protocols.
- Implement a MongoDB-backed `PersistenceProvider` that satisfies the same
  contract behavior as `InMemoryPersistenceProvider`, including deterministic
  reads, duplicate-key failures, runnable-work queries, waiting-gate queries,
  lease lookups, tool-control queries, and append-only workflow events.
- Keep MongoDB, PyMongo, BSON, collection names, index definitions, connection
  lifecycle, and driver errors inside `src/hoisa/adapters/persistence/`.
- Add focused MongoDB contract tests that run against the local Compose service
  when explicitly configured, and skip with a clear reason when MongoDB or
  Docker is unavailable.
- Preserve Hoisa's public/private boundary: no real local DB state, private
  target-repo data, credentials, raw logs, expanded connection strings, or
  local paths should be committed, printed, or posted.

## Decision
- Use PyMongo's current async API, `pymongo.AsyncMongoClient`, not Motor. MongoDB
  documents Motor as deprecated in favor of PyMongo Async, so adding Motor would
  knowingly create a short-lived dependency path.
- Add PyMongo as a normal project dependency, with a `4.x` constraint and a
  minimum version that includes the GA async API. The expected shape is
  `pymongo>=4.13,<5`, unless implementation-time dependency resolution shows a
  tighter current minimum is required.
- Add `src/hoisa/adapters/persistence/mongodb.py` with:
  - `MongoPersistenceConfig` or an equivalent small immutable configuration
    value for database name, timeout, and optional index initialization choices;
  - `MongoPersistenceProvider`, implementing `PersistenceProvider`;
  - adapter-only repository classes for each current port;
  - adapter-only collection specs and index specs.
- Use stable Hoisa IDs as MongoDB `_id` values while retaining the public
  stable ID fields in the stored document. For example, a `WorkItem` document
  stores `_id == work_item_id` and also stores `work_item_id` for Pydantic
  validation and portable fixtures.
- Do not expose `_id`, `ObjectId`, `InsertOneResult`, `DuplicateKeyError`,
  sessions, transactions, collection objects, or raw BSON documents through the
  port surface.
- Serialize Pydantic records through adapter-owned conversion helpers:
  - `model_dump(mode="python")` or an equivalent path that preserves datetime
    values as datetimes for MongoDB date indexes;
  - recursive conversion of enums and other non-BSON Python values to adapter
    storage values;
  - explicit `_id` injection on write;
  - explicit `_id` removal and Pydantic validation on read.
- Decode MongoDB datetimes as timezone-aware UTC values before Pydantic
  validation. Hoisa's `UtcDatetime` validator rejects naive datetimes, and
  PyMongo returns naive UTC datetimes by default unless configured otherwise.
  The preferred strategy is adapter-owned `CodecOptions(tz_aware=True,
  tzinfo=UTC)` applied at the database or collection boundary. If implementation
  discovers a driver limitation for nested documents, add an explicit recursive
  UTC-awareness conversion before domain model validation.
- Treat current-state repository `save()` calls as snapshot upserts. Replacing
  the same stable ID is allowed; colliding declared unique composite identities
  must raise `DuplicateRecordError`.
- Treat workflow event `append()` as insert-only. Duplicate `event_id` must
  raise `DuplicateRecordError`, and event query results must be deterministic
  by `happened_at` plus `event_id`.
- Keep transaction decisions adapter-owned and conservative for this issue:
  single repository methods use single-document upserts/inserts; no transaction
  API is added to the persistence port. If a future service needs atomic
  multi-document handoff, it should add an approved adapter-owned unit of work
  instead of leaking sessions through existing ports.

## Implementation Approach
- Add PyMongo dependency to `pyproject.toml` and update `uv.lock`.
- Add `src/hoisa/adapters/persistence/mongodb.py`.
- Implement a small internal collection/index description, for example:
  - collection name;
  - stable ID field;
  - model type;
  - unique indexes;
  - query indexes;
  - optional partial-filter behavior for nullable composite keys.
- Provide an explicit `ensure_indexes()` method on `MongoPersistenceProvider`.
  This method is not part of `PersistenceProvider`; it is an adapter lifecycle
  hook used by tests and future service wiring.
- Implement repositories for the existing port properties:
  - `projects`
  - `target_repos`
  - `source_connections`
  - `source_observations`
  - `sync_cursors`
  - `work_items`
  - `workflow_states`
  - `gates`
  - `agent_runs`
  - `evidence_bundles`
  - `tool_connections`
  - `tool_policies`
  - `action_requests`
  - `tool_invocations`
  - `workflow_events`
- Reuse a small internal generic snapshot helper only where it removes real
  duplication, such as save/get/list-by-field. Keep behavior-rich repository
  methods named by port use case instead of growing a public generic CRUD API.
- Implement adapter-neutral error conversion:
  - `pymongo.errors.DuplicateKeyError` -> `DuplicateRecordError`;
  - missing required documents remain `None` where the port returns optional
    records;
  - unexpected driver failures remain adapter-local or are wrapped in
    `PersistenceError` without logging credentials or document contents.
- Implement deterministic queries to match the memory adapter:
  - `ProjectRepository.list_all()` by `project_id`;
  - `TargetRepoRepository.list_by_project()` by `target_repo_id`;
  - `SourceObservationRepository.find_by_source()` by `observation_id`;
  - `SyncCursorRepository.list_by_source()` by `cursor_id`;
  - `WorkItemRepository.find_runnable()` by `created_at`, then
    `work_item_id`;
  - `WorkflowStateRepository` lease queries by `updated_at`, then
    `work_item_id`;
  - `ApprovalGateRepository` waiting/list queries by `created_at`, then
    `gate_id`;
  - run, evidence, tool-control, and event queries using the same ordering as
    the in-memory adapter.
- Keep join-like repository semantics visible and covered:
  - `WaitingGateQuery(tracker_issue_number=...)` depends on the related
    `WorkItem.tracker_issue`;
  - `ToolInvocationRepository.list_by_tool_action(project_id=...)` depends on
    the linked `ActionRequest.project`;
  - these may be implemented through bounded Python combination in the first
    adapter, but contract tests must make the cross-record behavior explicit.
- Implement runnable-work behavior to mirror the memory adapter exactly:
  - use `WorkflowStateRecord` state when present;
  - fall back to fields on `WorkItem` when no workflow-state record exists;
  - exclude active leases when `query.now` is present and the lease expires
    after `query.now`;
  - exclude active blockers unless `include_blocked=True`;
  - support project, target repo, risk, status, and workflow-stage filters.
- Keep query implementation simple and correct before optimizing. If the first
  MongoDB implementation needs to combine work-item and workflow-state
  documents in Python after bounded indexed reads, that is acceptable for this
  slice as long as the indexes are explicit and the contract tests prove the
  behavior.
- Add or update docs only where needed for local test setup, likely
  `deploy/local/README.md`, without committing real `.env` values or expanded
  connection strings.
- Do not wire the MongoDB provider into a service loop, CLI command, GitHub
  helper, tracker adapter, source sync adapter, or runner in this issue.

## Collection Mapping And Indexes
- `projects`
  - `_id`: `project_id`
  - unique: `_id`
  - query: `project_id`
- `target_repos`
  - `_id`: `target_repo_id`
  - unique: `_id`
  - unique: `provider`, `owner`, `name`
  - query: `project.project_id`, `target_repo_id`
- `source_connections`
  - `_id`: `source_connection_id`
  - unique: `_id`
  - query: `project.project_id`, `target_repo.target_repo_id`,
    `source_system`, `status`
- `source_observations`
  - `_id`: `observation_id`
  - unique: `_id`
  - unique: `source_connection_id`, `external_id`, `content_hash.value`
  - query: `source_connection_id`, `external_id`, `content_hash.value`
- `sync_cursors`
  - `_id`: `cursor_id`
  - unique: `_id`
  - unique: `source_connection_id`, `cursor_name`
  - query: `source_connection_id`, `cursor_name`
- `work_items`
  - `_id`: `work_item_id`
  - unique: `_id`
  - unique partial: `tracker_issue.provider`, `tracker_issue.issue_number`
    where `tracker_issue` exists
  - query: `target_repo.project.project_id`, `target_repo.target_repo_id`
  - query: `workflow_stage`, `status`, `risk`, `created_at`, `work_item_id`
- `workflow_states`
  - `_id`: `work_item_id`
  - unique: `_id`
  - query: `state.stage`, `state.status`, `state.risk`
  - query: `state.lease.worker_id`, `state.lease.expires_at`
  - query: `updated_at`, `work_item_id`
- `approval_gates`
  - `_id`: `gate_id`
  - unique: `_id`
  - query: `work_item_id`, `gate_status`, `workflow_stage`
  - query: `gate_status`, `created_at`, `gate_id`
- `agent_runs`
  - `_id`: `run_id`
  - unique: `_id`
  - query: `work_item_id`, `workflow_stage`, `started_at`, `run_id`
- `evidence_bundles`
  - `_id`: `bundle_id`
  - unique: `_id`
  - query: `subject_type`, `subject_id`, `bundle_id`
- `tool_connections`
  - `_id`: `tool_connection_id`
  - unique: `_id`
  - query: `project.project_id`, `tool_type`, `status`
- `tool_policies`
  - `_id`: `tool_policy_id`
  - unique: `_id`
  - unique: `project.project_id`, `tool_type`, `action_type`
  - query: `project.project_id`, `tool_type`, `action_type`
- `action_requests`
  - `_id`: `action_request_id`
  - unique: `_id`
  - query: `status`, `required_gate_id`, `created_at`
  - query: `project.project_id`, `tool_type`, `action_type`
- `tool_invocations`
  - `_id`: `tool_invocation_id`
  - unique: `_id`
  - query: `action_request_id`, `happened_at`
  - query: `tool_type`, `action_type`, `status`, `happened_at`
- `workflow_events`
  - `_id`: `event_id`
  - unique: `_id`
  - query: `subject.subject_type`, `subject.subject_id`, `happened_at`,
    `event_id`
  - query: `correlation_id`, `happened_at`, `event_id`
  - query: `happened_at`, `event_id`

## Interfaces
- New adapter import:
  - `hoisa.adapters.persistence.mongodb.MongoPersistenceProvider`
  - `hoisa.adapters.persistence.mongodb.MongoPersistenceConfig`, if the
    implementation uses a config value object.
- Provider construction should support tests and future service wiring without
  reading secrets from source files:
  - `MongoPersistenceProvider(client, database_name=...)`, or equivalent;
  - `MongoPersistenceProvider.from_uri(uri, database_name=...)`, if useful for
    tests and local setup;
  - `await provider.ensure_indexes()`;
  - `await provider.close()` or an async context manager for client shutdown.
- Existing public port interfaces remain unchanged:
  - `hoisa.ports.persistence.PersistenceProvider`
  - all repository protocols in `src/hoisa/ports/persistence.py`
  - adapter-neutral exceptions in `src/hoisa/ports/persistence.py`
- Test configuration should be explicit and skip-safe:
  - `HOISA_MONGO_TEST_URI` points at the local developer MongoDB instance;
  - `HOISA_MONGO_TEST_DATABASE` must be a generated or clearly test-only name,
    preferably beginning with `hoisa_test_`;
  - MongoDB contract tests skip if either variable is missing;
  - tests must refuse to drop or clean a database whose name does not begin
    with the allowed test prefix.
- The adapter must not introduce any new domain, app, or port dependency on
  PyMongo, BSON, MongoDB collection names, or MongoDB config.

## Test Plan
- Refactor the current persistence contract tests so both adapters can run the
  same behavior checks:
  - keep `tests/contract/persistence/test_memory_adapter.py` or move shared
    behavior into a helper fixture module;
  - add `tests/contract/persistence/test_mongodb_adapter.py` that binds the
    same contract cases to `MongoPersistenceProvider`;
  - preserve memory adapter coverage as the fast default contract suite.
- MongoDB contract tests should:
  - connect only when `HOISA_MONGO_TEST_URI` and a safe
    `HOISA_MONGO_TEST_DATABASE` are set;
  - call `ensure_indexes()` before exercising repositories;
  - clean only the generated test database or adapter-owned test collections;
  - never print expanded connection strings, credentials, stored documents, raw
    logs, private target-repo identifiers, or local paths.
- Contract behavior to prove against both memory and MongoDB:
  - all repositories save and fetch by stable ID;
  - declared unique IDs and composite keys reject duplicates as
    `DuplicateRecordError`;
  - runnable-work queries match stage, status, risk, project/repo filters,
    active lease expiration, and blocker rules;
  - waiting-gate and lease queries return the same records and deterministic
    order as the memory adapter;
  - source observation, sync cursor, tool-policy, action request, tool
    invocation, run, evidence, and event queries match the existing contract
    semantics;
  - workflow events are append-only and query by subject, correlation, and
    recency deterministically;
  - Pydantic validation on reads reconstructs domain records without exposing
    `_id`, ObjectId, raw BSON, or PyMongo result types.
- MongoDB-specific tests should verify:
  - collection names are defined by explicit adapter specs;
  - index creation includes the unique and query indexes listed above;
  - duplicate-key driver failures are converted to `DuplicateRecordError`;
  - adapter serialization preserves timezone-aware datetimes as MongoDB date
    values and converts enum fields to storage values;
  - adapter reads return timezone-aware UTC datetimes after a MongoDB
    round-trip for root timestamps (`created_at`, `updated_at`), workflow
    leases/blockers, gates, run timestamps, tool invocation timestamps, and
    workflow event `happened_at`;
  - join-like query semantics match the in-memory adapter for waiting gates by
    tracker issue and tool invocations by linked action request project;
  - architecture tests still prevent PyMongo/Motor imports from domain,
    application, and port modules.
- Local runtime validation:
  - if Docker Compose is available, run the MongoDB contract suite against the
    local Compose service from `deploy/local/`;
  - if Docker is unavailable, document the skip reason in the PR while still
    running memory contracts and unit/architecture checks.
- Required checks before PR:
  - `uv run python -m py_compile scripts/github/agent_workflow.py`
  - `uv run ruff check .`
  - `uv run ruff format --check .`
  - `uv run mypy scripts src tests`
  - `uv run pytest`
  - MongoDB contract tests against local Compose, or a documented skip with the
    exact missing local prerequisite.
- Acceptance mapping:
  - same-contract requirement is met when the shared contract suite runs for
    both `InMemoryPersistenceProvider` and `MongoPersistenceProvider`;
  - explicit collection/index requirement is met by adapter specs plus
    index-inspection tests;
  - adapter-boundary requirement is met by architecture tests, type checks, and
    no PyMongo/BSON values crossing ports;
  - public/private requirement is met by safe fixtures, skipped secret output,
    and no committed local DB state.

## Risks
- Risk level: high, matching issue metadata and helper classification.
- Durable local-state risk: MongoDB may contain private orchestration state.
  Mitigate with test-only database prefixes, no committed local data, no raw
  document logging, and no automatic cleanup outside generated test databases.
- Credential leakage risk: connection URIs can contain usernames/passwords.
  Mitigate by never printing expanded URIs or Compose config with secrets, and
  by documenting only placeholder connection-string shapes.
- Adapter-boundary risk: PyMongo types and `_id` behavior could leak into ports
  or domain records. Mitigate with adapter-only conversion helpers,
  architecture tests, and Pydantic revalidation on reads.
- Index/schema drift risk: MongoDB uniqueness can silently differ from memory
  behavior if indexes are missing. Mitigate with explicit index specs,
  `ensure_indexes()`, and index-inspection tests.
- Datetime decoding risk: PyMongo's default naive UTC reads would fail Hoisa
  domain validation or tempt adapter code to weaken timestamp requirements.
  Mitigate with adapter-owned timezone-aware codec options or recursive
  read-side UTC conversion, plus MongoDB round-trip tests for representative
  nested timestamps.
- Transaction ambiguity risk: future handoff operations may need current-state
  updates and event appends to be atomic. Mitigate by documenting that this
  issue does not add a cross-repository transaction port, and by keeping any
  future session/unit-of-work design adapter-owned and approval-gated.
- Overbuilding risk: a generic ODM, migration system, service wiring, or source
  sync path would expand the slice. Mitigate by implementing only the existing
  persistence ports, adapter lifecycle hooks, and tests needed for this issue.
- Dependency risk: adding PyMongo broadens runtime dependencies. Mitigate by
  using the official driver, pinning to the current major version, and keeping
  imports inside the adapter.
- Review route: `Review Both`. This plan should receive independent plan
  review before human implementation approval, and the implementation PR should
  receive independent review before the issue is considered implemented.
- Approval gate: approval authorizes only this MongoDB adapter, dependency,
  contract-test, safe local-test documentation, and index-spec slice. It does
  not authorize service-loop wiring, cloud MongoDB/Atlas, migrations,
  destructive local DB cleanup outside test databases, credential rotation,
  backup/retention policy, source sync, runner execution, or external writes.

## Simplification Check
- Reuse the existing persistence ports and in-memory contract behavior instead
  of designing a new storage API.
- Use PyMongo directly behind the adapter instead of adding an ODM.
- Keep generic repository helpers private and boring; public behavior remains
  the named Hoisa repository methods.
- Use `ensure_indexes()` and explicit specs instead of a migration framework.
- Do not add MongoDB schema validation in this issue unless it is needed to
  satisfy contract behavior cleanly. Indexes and Pydantic read/write validation
  are enough for the first durable adapter.
- Keep service configuration out of this slice. The adapter can accept a client
  or URI, but the future service loop should decide how to load local config
  and credentials.
- Keep all fixtures fake and public-safe.

## Assumptions
- Issues #9 and #10 have landed on `main`, so the persistence ports,
  in-memory adapter, memory contract tests, and local MongoDB Compose files are
  available for this implementation.
- A local developer MongoDB service is acceptable as the first durable test
  target, but tests must be skip-safe when Docker or MongoDB is unavailable.
- It is acceptable for the first MongoDB runnable-work query to prioritize
  correctness over server-side query sophistication, provided the indexes are
  explicit and future optimization can happen behind the same port.
- PyMongo Async is the correct driver path as of this plan date,
  2026-05-25, and PyMongo `4.13` is the first GA async lower bound supported
  by the cited MongoDB release notes.

## Out Of Scope
- Managed MongoDB Atlas or any cloud database setup.
- Production deployment, backup, retention, restore, credential rotation, or
  MongoDB application user provisioning.
- Service-loop wiring, CLI commands, GitHub source sync, runner behavior, or
  external tool writes.
- A migration framework or destructive write migration path.
- Public JSON schema expansion for every internal persistence record unless an
  existing public contract requires it.
- Reading, committing, printing, or exporting real local MongoDB contents.

## Sources
- Hoisa vision: `docs/vision.md`
- Hoisa workflow: `docs/github-workflow.md`
- Architecture direction: `docs/agent-plans/2-architecture-persistence-direction.md`
- Persistence ports and memory adapter plan:
  `docs/agent-plans/9-task-add-persistence-ports-and-in-memory-adapter.md`
- Local MongoDB infrastructure plan:
  `docs/agent-plans/10-task-add-local-mongodb-development-infrastructur.md`
- PyMongo `AsyncMongoClient` and connection lifecycle:
  https://www.mongodb.com/docs/languages/python/pymongo-driver/current/connect/mongoclient/
- MongoDB Python driver and Motor deprecation notice:
  https://www.mongodb.com/docs/languages/python/
- PyMongo 4.13 release notes for PyMongo Async GA:
  https://www.mongodb.com/docs/languages/python/pymongo-driver/v4.13/reference/release-notes/
- PyMongo timezone-aware datetime decoding:
  https://www.mongodb.com/docs/languages/python/pymongo-driver/data-formats/dates-and-times/
- PyMongo index creation and duplicate-key behavior:
  https://www.mongodb.com/docs/languages/python/pymongo-driver/current/indexes/
- MongoDB unique indexes:
  https://www.mongodb.com/docs/v8.0/core/index-unique/
- PyMongo BSON conversion:
  https://www.mongodb.com/docs/languages/python/pymongo-driver/current/data-formats/bson/
- PyMongo transactions:
  https://www.mongodb.com/docs/languages/python/pymongo-driver/current/crud/transactions/

## Revision History
- 2026-05-25: Initial plan scaffold.
- 2026-05-25: Filled implementation-ready plan for MongoDB persistence adapter.
- 2026-05-25: Addressed plan review by updating the PyMongo Async lower bound
  to the GA release and making timezone-aware MongoDB datetime decoding plus
  round-trip tests explicit.
