# Issue 2: Hoisa Architecture And Persistence Direction

Date: 2026-05-25
Issue: https://github.com/oryacobi/Hoisa/issues/2
Status: Spike recommendation updated with operator direction

## Summary

Hoisa should adopt a domain-oriented hexagonal architecture with explicit ports
for tracker, runner, filesystem/worktree, persistence, clock, notification, and
human-gate channels. This matches the product vision: Hoisa is not another
coding agent, but an operating layer that turns human direction into bounded
work, durable gates, agent packets, evidence bundles, and workflow history.

MongoDB is the selected first durable persistence adapter, but it should not be
treated as the architecture. The architecture should define typed repository and
event-store ports first, ship with in-memory/fake adapters for tests, and add a
MongoDB adapter behind those ports when durable storage is implemented.

Hoisa's durable database is local/private infrastructure next to the developer,
not a public artifact and not a managed cloud dependency. The local Hoisa DB
should be able to serve multiple projects and repositories for the user. Public
Hoisa repository artifacts may contain schemas, fake fixtures, generic plans,
and redacted examples only; they must not contain target-repo data.

Hoisa's DB should be the source of truth for agent work. External systems such
as GitHub, Slack, chat conversations, and future dashboards are synchronization
surfaces and command channels. They can originate signals, display state, and
receive controlled updates, but the canonical work state, permissions, evidence,
agent runs, decisions, and history live in Hoisa's local/private DB.

The first data model should combine current-state documents with an append-only
workflow event log. Avoid pure event sourcing for the first implementation:
Hoisa needs queryable audit history, but it also needs simple current-state
reads for "next work", active leases, pending gates, and PR handoff.

The first runtime should be a small long-running local service with CLI control
surfaces, backed by self-managed MongoDB in Docker Compose and a first runner
adapter for Codex in a Hoisa-managed Docker sandbox. OpenHands should remain a
strong comparison point and likely future runner adapter, but not the first
default control plane.

## Operator Direction

- Persistence: commit to MongoDB as the first durable adapter after fake and
  in-memory test adapters.
- Deployment: Hoisa should raise its own local MongoDB through Docker Compose;
  no managed Atlas/cloud database is in scope for the pilot.
- Runtime shape: assume a small long-running local service from the start, with
  CLI commands as one control surface over that service.
- Data boundary: persist no target-repo data publicly. The durable Hoisa DB is
  local/private and may serve multiple user projects and repositories.
- Source of truth: Hoisa's local/private DB owns canonical agent work state.
  GitHub, Slack, conversations, and future tools are synced external sources or
  controlled action surfaces.
- Runner: make Codex in Docker the first runner adapter. Evaluate OpenHands as
  an important alternative and likely follow-up adapter.
- Review route: skip independent agent review for this architecture decision
  for now; the operator owns that gate.

## Baseline Direction Decisions

### Accepted

- Use hexagonal architecture. Alistair Cockburn's ports-and-adapters framing is
  the right fit because Hoisa must swap external systems without changing core
  workflow behavior: GitHub today, other trackers later; local agents today,
  other runners later; MongoDB today, another store later.
- Organize packages around Hoisa's orchestration domains rather than technical
  layers alone.
- Do not call MongoDB directly from business logic. Core workflow code should
  depend on typed ports and domain services.
- Use Pydantic models for boundary validation, persistence DTOs, schemas, and
  event envelopes.
- Record agent actions, outcomes, evidence, review events, and retrospective
  signals as structured data from the start.
- Keep public/private boundaries as architecture constraints, not policy text
  alone.
- Use MongoDB as the first durable adapter behind the persistence ports.
- Start with a small local service process rather than a CLI-only architecture.
- Treat the local Hoisa database as private multi-project user infrastructure.
- Use Codex in a Hoisa-managed Docker sandbox as the first runner adapter.
- Make Hoisa's DB the canonical source of truth for work state, actions,
  decisions, evidence, and agent history.
- Mediate external tool reads and writes through Hoisa service ports and
  policy, not direct agent access.

### Changed

- Change "Hoisa owns its own database, first candidate MongoDB" to "Hoisa owns
  local/private durable orchestration state through persistence ports; MongoDB
  is the selected first durable adapter." This commits the first adapter without
  leaking MongoDB concerns into domain code.
- Change "most persisted models represent MongoDB collections" to "collection
  roots represent aggregate/document roots; nested value objects remain embedded
  Pydantic models." This prevents a one-class-per-collection habit.
- Change "provider/adapter should infer the collection from model type" to
  "collection mapping should be explicit per repository or aggregate root, with
  optional conventions." Inference is useful for reducing boilerplate, but
  explicit mapping makes migrations, indexes, privacy classification, and
  collection renames safer.
- Change "`BaseEntity` for all persisted models" to "`BaseEntity` for
  collection-root documents only." Nested value objects and event payloads should
  not inherit database identity by default.
- Change "Pydantic models are the domain model" to "Pydantic can be the initial
  domain representation for simple records, but domain services and ports own
  behavior and invariants." If richer invariants emerge, split domain objects
  from persistence DTOs.
- Change "public/private boundary means only redacted state can be persisted" to
  "public artifacts persist no target-repo data; the local/private Hoisa DB may
  hold private multi-project orchestration state."
- Change "GitHub issue/project metadata is the source of workflow state" to
  "GitHub is one synchronized source and output surface; Hoisa's local DB owns
  canonical workflow state, with source provenance retained for audit."

### Rejected

- Reject direct MongoDB access in core workflow code.
- Reject an ODM-first architecture. Hoisa needs explicit workflow boundaries
  and test doubles more than database convenience.
- Reject pure event-log-first persistence for the first implementation. It is
  too much operational and projection complexity before the POC proves its
  query needs.
- Reject storing private target-repo content, raw logs, secrets, local paths, or
  business-specific plans in public Hoisa artifacts.
- Reject a cloud-first database requirement for the pilot.
- Reject Codex Cloud as the first default runner because the pilot should run
  locally next to the developer.
- Reject adopting OpenHands as the whole Hoisa control plane. It may be a runner
  backend, but Hoisa should own project orchestration, gates, and evidence.
- Reject letting agents call external write tools directly. External writes
  must pass through Hoisa-controlled action policies, gates, and audit records.

## Proposed Source Tree

```text
src/hoisa/
  __init__.py
  service/
    main.py
    lifecycle.py
    scheduler.py
    config.py
  cli/
    main.py
    commands/
      serve.py
      inspect.py
      next.py
      packet.py
      gate.py
      status.py
  app/
    workflows/
      select_next_work.py
      build_task_packet.py
      build_gate.py
      record_handoff.py
    services/
      issue_quality.py
      risk_policy.py
      redaction.py
      source_sync.py
      task_packets.py
      tool_policy.py
  domain/
    directives.py
    external_sources.py
    work_items.py
    workflow_state.py
    gates.py
    runs.py
    agents.py
    evidence.py
    events.py
    retrospectives.py
    target_repos.py
    tool_controls.py
  ports/
    external_action.py
    source_sync.py
    tracker.py
    persistence.py
    runner.py
    filesystem.py
    clock.py
    notifier.py
  adapters/
    external_sources/
      github.py
      slack.py
      fake.py
    tracker/
      github.py
      fake.py
    persistence/
      memory.py
      mongodb.py
    filesystem/
      local.py
      fake.py
    runner/
      codex_docker.py
      openhands.py
      fake.py
  schemas/
    public/
      gate.schema.json
      event.schema.json
      task_packet.schema.json
  privacy/
    classifiers.py
    redaction_rules.py
  tests/
    unit/
    contract/
    fixtures/
deploy/
  local/
    docker-compose.yml
    mongo-init/
```

Domain modules should define orchestration vocabulary and invariants:

- `directives`: human intent, constraints, approval preferences, target scope.
- `external_sources`: normalized records, source cursors, source provenance,
  and inbound signal classification for GitHub, Slack, conversations, and later
  tools.
- `work_items`: agent-ready units with quality, risk, blockers, and evidence
  requirements.
- `workflow_state`: lifecycle stages, queue status, leases, review routes, and
  state transitions.
- `gates`: structured human decisions and single-use authority boundaries.
- `runs`: disposable agent attempts, runner profiles, budgets, results, and
  check summaries.
- `evidence`: links, hashes, summaries, redaction status, and provenance.
- `events`: append-only workflow history for audit and retrospectives.
- `target_repos`: local/private repository and project references for the
  user's Hoisa database; public exports must redact or omit private details.
- `tool_controls`: per-project external tool permissions, action requests,
  action approvals, and invocation audit records.

Application workflows should orchestrate domain services and ports. Adapters
should translate GitHub, filesystem, runner, and database details into those
ports.

## Persistence Recommendation

Implement fake/in-memory adapters first for contract tests, then MongoDB as the
first durable adapter. Do not build a SQLite durable path for the first POC
unless MongoDB becomes blocked.

### Local Private Store

Hoisa's MongoDB is local/private infrastructure for the user. It may store
private orchestration data for multiple projects and repositories, including
repo identifiers, workflow state, gates, run summaries, evidence references,
and local/private locators. This data must not be committed, published into the
public Hoisa repository, or mirrored into public issue comments.

Redaction is required at export boundaries:

- public Hoisa docs, plans, schemas, and fixtures;
- GitHub comments or issues in public repositories;
- support bundles or bug reports;
- shared screenshots, logs, and review artifacts.

The local DB should carry project and repository scope on every operational
record so a single developer-local service can coordinate multiple repos:

```text
project_id
target_repo_id
provider
owner_or_namespace
repo_name
local_worktree_root
privacy_class
```

### DB Source Of Truth

Hoisa's local/private DB should contain everything required to understand,
resume, review, and improve agent work without reconstructing state from a chat
transcript, GitHub timeline, Slack thread, terminal log, or runner session.

Canonical records should live in Hoisa first:

- project and repository registry;
- external source connections and sync cursors;
- normalized external artifacts such as issues, PRs, comments, review threads,
  Slack messages, and conversation turns;
- directives and work items;
- workflow stage, status, leases, blockers, and review route;
- plans, gates, gate decisions, and exact authority granted;
- task packets and context selections;
- agent runs, runner configuration, budgets, commands, checks, and outcomes;
- evidence bundles, artifact hashes, diffs, PR links, and local/private
  locators;
- tool policies, action requests, external tool invocations, and write results;
- append-only workflow events for every meaningful state transition.

External systems are not ignored. Hoisa should sync them into canonical local
records with provenance:

```text
source_system: github | slack | conversation | filesystem | runner
source_connection_id
external_id
external_url
external_updated_at
observed_at
sync_cursor
content_hash
normalization_version
privacy_class
raw_snapshot_ref
canonical_record_ref
```

Because the DB is local/private, it may store private normalized content needed
for agent work and later review. Raw external snapshots should still be
deliberate: store them when they improve auditability or resync, otherwise keep
hashes and compact normalized forms. Public exports must go through redaction
and may omit private source content entirely.

### Synchronization Model

Each external integration should be a source connector with the same lifecycle:

1. Pull external changes using a source cursor, webhook, or manual sync command.
2. Store raw or normalized source observations with `observed_at`,
   `content_hash`, and source provenance.
3. Reduce observations into canonical Hoisa records through deterministic
   mappers.
4. Record a `source.synced` or `source.conflict_detected` event.
5. Expose proposed state changes to the workflow reducer.
6. Emit controlled external writes only through action requests and policies.

GitHub issue edits, Slack messages, or conversation turns can create signals,
but they should not directly mutate workflow state. They become observations
that Hoisa classifies, maps, and applies according to policy. This keeps a clean
line between "something happened outside" and "Hoisa accepted this as workflow
state."

Conflict policy:

- Hoisa-owned fields, such as workflow stage, lease, gate status, runner
  assignment, and internal evidence status, are authoritative in the DB.
- External-owned fields, such as GitHub title/body/comment text or Slack
  message text, sync from the external source into source observations.
- Shared fields, such as labels, public status comments, linked PRs, and review
  requests, require explicit reducer rules and conflict events when external
  state diverges.
- Human commands from external channels must be attributed, classified, and
  checked against policy before mutating canonical state.

### External Tool Control

Hoisa should own a tool-control layer before agents can use external systems.
Agents receive capabilities through task packets; they do not receive ambient
permission to post comments, change GitHub metadata, send Slack messages, push
branches, create PRs, or modify service configuration.

Model tool access as durable DB records:

```text
ToolConnection
  connection_id
  tool_type
  project_id
  target_repo_id
  credential_ref
  allowed_scopes
  default_policy
  status

ToolPolicy
  policy_id
  project_id
  tool_type
  action_type
  allowed_actor_roles
  allowed_workflow_stages
  risk_ceiling
  requires_gate
  rate_limit
  audit_level

ActionRequest
  action_request_id
  requested_by
  tool_type
  action_type
  target
  payload_summary
  risk
  required_gate_id
  status

ToolInvocation
  invocation_id
  action_request_id
  executed_by_service
  external_id
  result
  happened_at
  evidence_refs
```

Initial policy defaults:

- Read-only sync from GitHub is allowed for configured repositories.
- Posting public issue/PR comments requires the service policy to approve the
  action and must record the exact body in the DB first.
- Mutating labels, project fields, assignees, branches, or PR state requires an
  explicit policy and should usually require a gate until proven routine.
- Slack writes and conversational replies should start disabled except for
  local dry-run rendering.
- Secrets, credential changes, production-like systems, and privileged settings
  always require explicit human approval and should not be delegated to agents
  by default.

This gives Hoisa a clear answer to "what external tool does what": the DB holds
the connection, policy, requested action, approval, invocation, and result.

### Review And Learning Access

The DB schema should optimize not just execution but later review and
retrospective learning. Hoisa should be able to answer:

- What work did each agent attempt, with which context packet and permissions?
- Which external observations caused state changes?
- Which gates were approved, rejected, noisy, or useful?
- Which tool writes were requested, approved, denied, or failed?
- Which review comments changed outcomes?
- Which tasks got stuck because of sync conflicts, missing context, bad plans,
  failing checks, or unclear human direction?
- Which runner profiles and policies produced the least rework?

This requires queryable summaries in current-state records plus append-only
events with correlation IDs, causation IDs, source provenance, and evidence
references. It should never require reading the agent's terminal transcript as
the only record.

### Storage Shape

Use two persistence surfaces:

1. Current-state repositories for active workflow objects.
2. Append-only workflow events for audit, causation, and retrospective queries.

Recommended first collection/document roots:

- `projects`
- `repo_connections`
- `source_connections`
- `source_observations`
- `sync_cursors`
- `directives`
- `work_items`
- `workflow_items`
- `approval_gates`
- `agent_runs`
- `evidence_bundles`
- `tool_connections`
- `tool_policies`
- `action_requests`
- `tool_invocations`
- `workflow_events`
- `target_repos`
- `retrospective_reports`

The current-state records answer operational questions quickly. The event log
answers "what happened, why, by whom, from which evidence, and what changed?"

### MongoDB Fit

MongoDB fits the first durable adapter if Hoisa expects evolving document
shapes, embedded evidence summaries, heterogeneous event payloads, and
collection/database change subscriptions. MongoDB supports document validation,
unique indexes, and change streams, but schema design still matters: MongoDB's
own guidance says distributed transactions have higher cost than single-document
writes and should not replace effective schema design.

Use MongoDB this way:

- Run self-managed local MongoDB through `deploy/local/docker-compose.yml`, with
  persistent volumes and local-only credentials/configuration.
- Prefer one aggregate/document root per collection.
- Embed small value objects that are normally read with the parent.
- Reference large or independently changing artifacts by durable local/private
  locator and evidence hash instead of embedding raw content by default.
- Keep workflow transition writes single-document where practical.
- Use multi-document transactions sparingly for gate decisions or handoff steps
  that must update current state and append an event together.
- Define indexes with the repository contract, not ad hoc in application code.
- Use change streams later for loop wakeups and monitoring, not as the only
  source of durable workflow truth.

### Pydantic Entity Conventions

Use Pydantic v2 models for validation and serialization at Hoisa boundaries.
Pydantic's current docs support typed models, `default_factory`, aliases, and
distinct validation/serialization aliases, which are useful for `_id` and public
schema names.

Suggested conventions:

```python
class BaseEntity(BaseModel):
    id: str = Field(validation_alias="_id", serialization_alias="_id")
    created_at: datetime
    updated_at: datetime
    schema_version: int = 1
```

- Use `BaseEntity` only for collection-root records.
- Use timezone-aware UTC timestamps.
- Prefer application-generated stable IDs for Hoisa entities. MongoDB ObjectIds
  are fine internally, but opaque string IDs simplify GitHub comments, event
  causation, and fixtures.
- Include `schema_version` on collection roots and event envelopes.
- Make `created_at` immutable after insert; update `updated_at` only through the
  persistence port.
- Keep raw driver/BSON types out of domain code. Convert ObjectId, datetime,
  and driver errors in the adapter.
- Use `model_dump(by_alias=True)` for MongoDB writes and explicit model
  validation on reads.

### Provider And Adapter APIs

Define persistence ports around use cases, not around generic database access.
Generic CRUD can sit underneath adapter internals, but application code should
call intention-revealing ports:

```python
class WorkItemRepository(Protocol):
    async def get(self, work_item_id: str) -> WorkItem | None: ...
    async def save(self, work_item: WorkItem) -> None: ...
    async def find_runnable(self, query: RunnableWorkQuery) -> list[WorkItem]: ...

class GateRepository(Protocol):
    async def get_waiting_for_issue(self, issue_ref: IssueRef) -> list[ApprovalGate]: ...
    async def record_decision(self, decision: GateDecision) -> ApprovalGate: ...

class EventStore(Protocol):
    async def append(self, event: WorkflowEvent) -> None: ...
    async def list_for_subject(self, subject: EventSubject) -> list[WorkflowEvent]: ...
```

The MongoDB adapter can use a small internal typed collection provider:

```python
class MongoCollectionProvider(Protocol):
    def collection_for(self, entity_type: type[BaseEntity]) -> AsyncCollection: ...
```

The mapping should be explicit:

```python
COLLECTIONS = {
    WorkItem: "work_items",
    ApprovalGate: "approval_gates",
    AgentRun: "agent_runs",
    WorkflowEvent: "workflow_events",
}
```

### Indexing

Define indexes alongside repositories and verify them in adapter contract tests.
Likely first indexes:

- `projects`: `(project_id)`, unique.
- `repo_connections`: `(target_repo_id)`, unique.
- `repo_connections`: `(provider, owner_or_namespace, repo_name)`.
- `source_connections`: `(source_connection_id)`, unique.
- `source_observations`: `(source_connection_id, external_id, content_hash)`.
- `sync_cursors`: `(source_connection_id, cursor_name)`, unique.
- `work_items`: `(target_repo_id, tracker_issue_number)`, unique.
- `work_items`: `(status, workflow_stage, risk, lease_expires_at)`.
- `approval_gates`: `(gate_status, issue_ref, created_at)`.
- `approval_gates`: `(gate_id)`, unique.
- `agent_runs`: `(run_id)`, unique.
- `agent_runs`: `(work_item_id, workflow_stage, started_at)`.
- `workflow_events`: `(event_id)`, unique.
- `workflow_events`: `(subject_type, subject_id, happened_at)`.
- `workflow_events`: `(correlation_id, happened_at)`.
- `evidence_bundles`: `(bundle_id)`, unique.
- `tool_policies`: `(project_id, tool_type, action_type)`.
- `action_requests`: `(status, required_gate_id, created_at)`.
- `tool_invocations`: `(tool_type, action_type, happened_at)`.
- `target_repos`: `(provider, owner_or_namespace, repo_name)`.

Avoid selecting by raw private content when stable IDs or hashes will do.
Prefer indexes on project/repo IDs, status fields, timestamps, risk class, gate
status, and evidence hashes. Keep adapter logs from printing indexed private
values.

### Migration And Versioning

Do not introduce a migration framework before the first durable adapter exists,
but design for one:

- Every collection root and event envelope carries `schema_version`.
- Adapters own read migrations from older versions to current domain models.
- Destructive write migrations require a human approval gate.
- Store migration events in `workflow_events`.
- Keep JSON Schema files for public event and gate contracts in `schemas/public`.
- Contract tests should load all public fixtures and validate current schemas.

## Structured Action And Evidence Model

Use an append-only `WorkflowEvent` envelope:

```text
event_id
event_type
happened_at
actor_type
actor_id
subject_type
subject_id
correlation_id
causation_id
workflow_stage
risk
public_safety_class
payload_schema
payload
evidence_refs
redaction_status
```

Core event families:

- `directive.captured`
- `source.synced`
- `source.conflict_detected`
- `issue.quality_checked`
- `work_item.selected`
- `lease.claimed`
- `task_packet.created`
- `plan.created`
- `plan.review_requested`
- `gate.created`
- `gate.decided`
- `agent_run.started`
- `agent_run.completed`
- `checks.completed`
- `action.requested`
- `action.approved`
- `action.denied`
- `tool.invoked`
- `tool.failed`
- `pr.opened`
- `review.requested_changes`
- `review.ready`
- `handoff.created`
- `incident.recorded`
- `retrospective.created`

Use separate current-state records for `AgentRun`, `EvidenceBundle`, and
`ApprovalGate`. Events should include references and compact summaries, not raw
logs. Evidence bundles can point to repo-local files, PRs, check runs, plan
files, or redacted summaries with hashes.

## Service And Runner Recommendation

### Local Service

The first implementation should assume a small long-running local service, not
only one-shot CLI commands. CLI commands should call into this service or share
the same application layer.

The service owns:

- MongoDB connection lifecycle;
- project/repo registry;
- external source sync loops and sync cursors;
- workflow polling or watch loops;
- lease and stale-work handling;
- tool policy checks and external action dispatch;
- runner dispatch;
- event recording;
- local status APIs for later UI, voice, or notification surfaces.

Keep the service boring: one process, one local config file, explicit shutdown,
structured logs, and a health/status command.

### Codex Docker Runner

Use Codex in Docker as the first runner adapter. OpenAI's current Codex CLI docs
describe Codex as a local coding agent that can read, change, and run code in a
selected directory. OpenAI's local-shell docs say command execution happens in
the user's own runtime and explicitly recommend sandboxing arbitrary shell
execution. Hoisa should therefore own the Docker sandbox around Codex rather
than depending on Codex Cloud for the first runner.

Initial runner shape:

- create or select a clean worktree for the target repo;
- start a per-run Docker container from a Hoisa-controlled image;
- mount the worktree at `/workspace` read-write;
- mount Hoisa task packets and approved context read-only;
- inject only the runner credentials needed for Codex, never MongoDB root
  credentials or unrelated host secrets;
- run Codex non-interactively when possible, or through a thin local-shell loop
  if the CLI surface is not sufficient;
- disable network by default unless a task has an explicit network approval
  gate;
- collect diff, command summary, check results, logs, and evidence hashes back
  through the runner port;
- destroy the container after the run.

The runner adapter should not know GitHub workflow rules. It receives a bounded
task packet and returns a run result.

### OpenHands Comparison

OpenHands is a credible runner candidate. Its official docs describe Docker as
the default/recommended local sandbox, with the agent server running inside a
Docker container and local repositories mounted into `/workspace`. Its runtime
architecture is broader than a simple runner: it includes bash execution,
browser interaction, filesystem operations, plugins, event streams, and local
resource management.

That makes OpenHands attractive as a future adapter, especially for browser
tasks or richer action execution. For the first Hoisa slice, it is also heavier
and overlaps with the control-plane responsibilities Hoisa is trying to define.
Recommendation: implement `CodexDockerRunner` first and create a follow-up
spike or adapter task for `OpenHandsRunner` after the runner port is stable.

## Tradeoffs

### Flat Files

Flat files are excellent for public schemas, durable plan artifacts, fake
fixtures, and local review. They are weak for active leases, concurrent agents,
queries across workflow history, and change notifications. Use them for plans,
fixtures, and evidence references; do not make them the primary state store once
Hoisa coordinates multiple active runs.

### SQLite

SQLite is a strong first local store: simple setup, transactional, easy to
vendor into a CLI, and now has built-in JSON support. Its own docs still state
there can be only one simultaneous writer, even though WAL lets readers and a
writer coexist. That is acceptable for a local POC, but less attractive for
multi-run orchestration or a long-running local service. Operator direction
selects MongoDB for the first durable adapter, so SQLite should be deferred.

### Postgres

Postgres is the safest long-term choice if Hoisa needs relational integrity,
rich joins, mature migrations, analytics, and JSONB in one store. It is heavier
for a self-hosted research POC and can pull the first implementation toward
schema design before the workflow model stabilizes.

### MongoDB

MongoDB best matches evolving workflow documents and heterogeneous event
payloads. Its tradeoff is that correctness depends on disciplined aggregate
design, explicit indexes, schema validation, and adapter boundaries. It is a
good first durable adapter, not something core domain code should know about.
For the pilot, it should be self-managed locally with Docker Compose and
persistent volumes.

### Direct MongoDB Access

Direct access is fast to start but would couple business logic to query shape,
collection names, driver errors, BSON behavior, and transaction choices. It
also makes fake adapters and public/private contract tests harder. Reject it.

### Event-Log-First Persistence

Event-log-first gives strong auditability and retrospective power, but pure
event sourcing adds projection rebuilds, versioned event semantics, replay
discipline, and operational complexity. Hoisa should record append-only events
from day one while keeping current-state documents as the operational source for
selection, gates, leases, and status.

## Architecture Contract Tests

Add tests early to prevent architecture drift:

- Domain modules do not import adapters, PyMongo, GitHub clients, filesystem
  implementations, or runner implementations.
- Application workflows import ports, not concrete adapters.
- Adapters may import domain and ports; domain may not import adapters.
- Public schemas and fixtures contain no private-looking local paths, secrets,
  target-repo business names, raw logs, or screenshots.
- Persistence adapters pass the same repository contract tests as memory/fake
  adapters.
- Event fixtures validate against public JSON Schemas.
- Redaction tests prove private target-repo content is summarized, omitted, or
  rejected before public export.

## Risk Assessment

Risk: Medium-high for architecture direction, low for this planning artifact.

Primary risks:

- Public/private leakage. Mitigation: privacy classifiers, public-safe schema
  contracts, redaction tests, export-boundary checks, and never committing or
  publishing local Hoisa DB contents.
- Local DB sensitivity. Mitigation: local-only defaults, documented backup and
  retention policy, no cloud database dependency, and credential isolation
  between Hoisa, MongoDB, and runner containers.
- Source-of-truth confusion. Mitigation: DB-owned canonical workflow fields,
  explicit external source observations, deterministic reducers, and conflict
  events whenever external state diverges from Hoisa state.
- External tool misuse. Mitigation: DB-backed tool policies, action requests,
  gates for write or privileged actions, service-mediated invocation, and an
  append-only invocation audit trail.
- Schema evolution. Mitigation: `schema_version`, explicit migrations,
  adapter-owned read upgrades, and public fixture validation.
- Audit gaps. Mitigation: append workflow events for selection, gates, runs,
  checks, handoffs, reviews, and incidents from the first durable slice.
- Overbuilding. Mitigation: implement ports and fake adapters first; add
  MongoDB only behind tested contracts.
- MongoDB lock-in. Mitigation: no PyMongo imports outside adapters and no
  collection names in domain/application code.
- Runner containment. Mitigation: per-run Docker containers, minimal mounts,
  no ambient host secrets, network disabled by default, and run evidence
  returned through typed ports.
- Testability. Mitigation: memory adapter, fake tracker, fake runner, contract
  tests, and architecture import tests.
- Human-gate ambiguity. Mitigation: approval gates state exact authority,
  evidence, risk, and single-use options.

## Proposed Implementation Task Graph

1. Create the initial Python package skeleton, local service shell, and
   architecture contract tests.
   Acceptance: domain/app/ports/adapters/service boundaries exist; tests fail
   if domain imports adapters or external clients.
2. Add local Docker Compose infrastructure for self-managed MongoDB.
   Acceptance: `docker compose up` starts MongoDB with persistent volumes,
   local credentials, and a documented local connection string.
3. Define public Pydantic schemas for `Directive`, `WorkItem`, `ApprovalGate`,
   `AgentRun`, `EvidenceBundle`, and `WorkflowEvent`.
   Acceptance: schemas export to `schemas/public`; fake fixtures validate.
4. Implement persistence ports and in-memory adapters.
   Acceptance: repository contract tests pass without external services.
5. Implement MongoDB persistence adapter behind the tested ports.
   Acceptance: the same repository contract tests pass against local MongoDB;
   indexes and schema validation are created or checked explicitly.
6. Implement local project/repo registry for a multi-project private Hoisa DB.
   Acceptance: records are scoped by project and target repo; public exports
   contain no private repo data unless explicitly redacted.
7. Implement source-of-truth records for external source observations, sync
   cursors, and canonical reducer provenance.
   Acceptance: GitHub-like fake observations reduce into canonical DB records
   with source provenance, content hashes, sync cursors, and conflict events.
8. Implement DB-backed tool control records and policy checks.
   Acceptance: fake external write requests are allowed, denied, or gated by
   `ToolPolicy`; every attempt creates `ActionRequest` and `ToolInvocation` or
   denial events.
9. Implement privacy classification and redaction tests for public artifacts.
   Acceptance: fixtures with private-looking paths, secrets, and raw logs are
   rejected or redacted.
10. Implement a read-only GitHub source sync adapter for issue/project metadata.
   Acceptance: `hoisa inspect` and `hoisa next --dry-run` produce public-safe
   summaries for public output, while canonical private state is stored in the
   local DB.
11. Implement task packet and gate card builders.
   Acceptance: `hoisa packet` and `hoisa gate` create bounded artifacts with
   exact authority and evidence refs.
12. Define the runner port and implement `CodexDockerRunner`.
    Acceptance: a fake runner and Codex Docker runner share contract tests;
    the Codex runner works in a disposable container with bounded mounts.
13. Add workflow event recording for dry-run transitions.
    Acceptance: selection, gate creation, and status summaries append
    structured events with correlation IDs.
14. Add retrospective query command over fake fixture history.
    Acceptance: command summarizes stuck work, noisy gates, review catches, and
    follow-up recommendations from public-safe data.
15. Create an OpenHands runner evaluation follow-up.
    Acceptance: issue compares OpenHands adapter scope against the stable
    runner port after Codex Docker establishes the first path.

## Resolved Human Direction

- MongoDB is the first durable adapter.
- Hoisa starts as a small long-running local service, not CLI-only.
- Public persistence of target-repo data is not allowed. The Hoisa DB is local,
  private, and multi-project.
- Hoisa's DB is the source of truth for agent work. External systems are synced
  sources or controlled action surfaces.
- External tool writes are mediated by Hoisa policies, gates, and audited
  action records.
- First runner adapter is Codex in Docker.
- Independent agent review is skipped for now by operator direction.
- MongoDB is self-managed locally with Docker Compose; no managed Atlas/cloud
  database is in scope for the pilot.

## Remaining Implementation Questions

- Which Codex authentication mode should the local runner use first: ChatGPT
  login, API key, or both?
- What is the first supported host OS matrix for the Hoisa-managed Docker
  runner?
- What default retention and backup policy should the private local MongoDB use?
- Should the first service API be internal-only CLI IPC, local HTTP, or both?
- For the first GitHub sync, which fields are DB-owned versus GitHub-owned
  versus shared reducer-owned?
- Which external write actions should be enabled in the first pilot after
  read-only sync: issue comments, project fields, labels, branch pushes, or PRs?

## Sources

- Hoisa vision: `docs/vision.md`
- Hoisa workflow: `docs/github-workflow.md`
- Hoisa orchestration research: `docs/research/human-agent-project-orchestration.md`
- Alistair Cockburn, Hexagonal Architecture:
  https://alistair.cockburn.us/hexagonal-architecture
- MongoDB data modeling best practices:
  https://www.mongodb.com/docs/manual/data-modeling/best-practices/
- MongoDB schema validation:
  https://www.mongodb.com/docs/manual/core/schema-validation/
- MongoDB unique indexes:
  https://www.mongodb.com/docs/v8.0/core/index-unique/
- MongoDB change streams:
  https://www.mongodb.com/docs/manual/changestreams/
- MongoDB Community Docker image:
  https://www.mongodb.com/docs/v8.0/tutorial/install-mongodb-community-with-docker/
- MongoDB local Docker Compose example:
  https://www.mongodb.com/docs/atlas/cli/current/atlas-cli-docker-compose/
- PyMongo `MongoClient` and `AsyncMongoClient`:
  https://www.mongodb.com/docs/languages/python/pymongo-driver/current/connect/mongoclient/
- Motor deprecation and PyMongo Async direction:
  https://www.mongodb.com/docs/drivers/motor/
- Pydantic models:
  https://docs.pydantic.dev/latest/concepts/models/
- Pydantic fields and aliases:
  https://docs.pydantic.dev/latest/concepts/fields/
- SQLite transactions:
  https://www.sqlite.org/lang_transaction.html
- SQLite JSON functions:
  https://www.sqlite.org/json1.html
- PostgreSQL transactions:
  https://www.postgresql.org/docs/current/tutorial-transactions.html
- PostgreSQL JSON types:
  https://www.postgresql.org/docs/current/datatype-json.html
- OpenAI Codex CLI:
  https://developers.openai.com/codex/cli
- OpenAI local shell tool:
  https://developers.openai.com/api/docs/guides/tools-local-shell
- OpenHands Docker sandbox:
  https://docs.openhands.dev/openhands/usage/sandboxes/docker
- OpenHands runtime architecture:
  https://docs.openhands.dev/openhands/usage/architecture/runtime

## Requested Next Action

This recommendation now incorporates operator direction. The next action should
be approval to create follow-up implementation issues for the task graph, then
approval of the first implementation slice. Approval should grant only authority
to build local/self-hosted Hoisa infrastructure and the first approved slice,
not broad permission to read unrelated secrets, contact production systems, or
publish target-repo data.

## Revision History

- 2026-05-25: Initial spike recommendation.
- 2026-05-25: Incorporated operator direction: MongoDB first, local service
  first, private multi-project DB, self-managed Docker Compose MongoDB, Codex
  Docker first runner, OpenHands as follow-up candidate.
- 2026-05-25: Added DB source-of-truth model, external source synchronization,
  tool policy/action request controls, and review/learning query requirements.
