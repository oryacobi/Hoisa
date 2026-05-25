---
issue: 6
title: "[Task]: Define core workflow, gate, run, evidence, and event models"
agent: Codex
branch: codex/6-task-define-core-workflow-gate-run-evidence-and
created: 2026-05-25
superseded_by:
linked_pr:
---

# Plan for #6: [Task]: Define core workflow, gate, run, evidence, and event models

## Summary
- Define the first Pydantic v2 model layer for Hoisa's orchestration
  vocabulary: projects/repos, directives, work items, workflow state, approval
  gates, gate decisions, agent runs, evidence bundles, task packets, and
  workflow events.
- Add public JSON Schema artifacts and fake public fixtures for the gate,
  event, task packet, and core current-state records that future adapters,
  task-packet builders, gate cards, and retrospective queries can rely on.
- Keep this as a domain and schema contract slice only. Persistence adapters,
  GitHub mapping, runner execution, service loops, and MongoDB collection code
  stay out of scope.

## Decision
- Use Pydantic v2 as the first domain/boundary representation for structured
  records, while keeping behavior and orchestration policy in domain services
  or application workflows in later issues.
- Add a small shared model foundation:
  - collection-root models carry type-specific stable IDs, `created_at`,
    `updated_at`, and `schema_version`;
  - nested value objects inherit only the plain Hoisa Pydantic model base and
    do not receive database identity, timestamps, or `schema_version` by
    default;
  - datetimes must be timezone-aware and normalized to UTC at validation
    boundaries;
  - model configs should forbid unknown fields so public schemas and fixtures
    catch drift early.
- Use semantic ID field names such as `work_item_id`, `gate_id`, `run_id`,
  `bundle_id`, `packet_id`, and `event_id` in public/domain models. MongoDB
  `_id` aliases remain a later persistence-adapter concern so public schemas do
  not expose adapter vocabulary.
- Model source provenance, public-safety classification, redaction status,
  correlation IDs, causation IDs, and evidence references explicitly, not as
  loose metadata dictionaries.
- Use checked-in public schemas under `src/hoisa/schemas/public/` and fake
  public fixtures under `tests/fixtures/public/`. Tests should regenerate schema
  documents from the model classes and compare them to the checked-in JSON so
  schema drift is caught without introducing a generation CLI yet.
- Add `pydantic>=2,<3` as a runtime dependency and update the lock file during
  implementation.
- Pydantic reference points used for this plan:
  - https://docs.pydantic.dev/latest/api/base_model/
  - https://docs.pydantic.dev/latest/concepts/fields/
  - https://docs.pydantic.dev/latest/concepts/alias/

## Implementation Approach
- Add or expand domain modules under `src/hoisa/domain/`:
  - `models.py`: shared `HoisaModel`, `CollectionRoot`, timestamp validation,
    and stable schema-version defaults.
  - `privacy.py` or equivalent domain vocabulary for `PublicSafetyClass` and
    `RedactionStatus`, unless the implementation cleanly places this in
    `src/hoisa/privacy/` without creating dependency cycles.
  - `provenance.py`: `SourceSystem`, `SourceProvenance`, and content/hash
    references for external observations.
  - `target_repos.py`: `ProjectRef`, `TargetRepoRef`, and generic repo/provider
    references that do not contain local paths in public fixtures.
  - `directives.py`: `Directive` collection root plus constraints, requested
    review route, risk, and source provenance.
  - `workflow_state.py`: queue status, workflow stage, review route, lease,
    blocker, and state-summary value objects. Keep compatibility with the
    existing `WorkflowStage` vocabulary in `work_items.py`, either by moving it
    here and re-exporting or by updating imports deliberately.
  - `work_items.py`: expand the current stub into a `WorkItem` collection root
    with issue/tracker references, risk, quality status, blockers,
    workflow/status fields, plan/PR refs, and evidence requirements.
  - `gates.py`: `ApprovalGate`, `GateDecision`, gate type/status/options,
    recommendation, exact authority granted, and evidence refs.
  - `runs.py`: `AgentRun`, runner profile, run budget, run result, check
    summary, and command/check evidence summaries.
  - `evidence.py`: `EvidenceBundle`, `EvidenceRef`, evidence kind, artifact
    hash, summary, provenance, and redaction/public-safety status. References
    should support issue/PR URLs, repo-relative paths, check runs, and redacted
    summaries without embedding raw logs.
  - `task_packets.py`: `TaskPacket` collection root with bounded context refs,
    allowed actions, approval authority, budget, runner profile, and evidence
    requirements.
  - `events.py`: append-only `WorkflowEvent` envelope with `event_type`,
    `happened_at`, actor, subject, workflow stage, risk, `correlation_id`,
    optional `causation_id`, `payload_schema`, compact payload, evidence refs,
    source provenance, public-safety class, redaction status, and
    `schema_version`.
- Keep field sets intentionally small but complete enough to express the issue
  acceptance criteria. Prefer enums and small value objects over free-form
  dictionaries for fields that affect workflow decisions.
- Do not add persistence repositories, MongoDB adapters, GitHub API mapping,
  runner execution, or service-loop behavior. If a model needs a future adapter
  field, represent it as a generic source/provenance or evidence reference.
- Add public schema support:
  - `src/hoisa/schemas/public/catalog.py` maps stable schema names to public
    model classes.
  - Checked-in JSON files include at least:
    - `directive.schema.json`
    - `work_item.schema.json`
    - `approval_gate.schema.json`
    - `agent_run.schema.json`
    - `evidence_bundle.schema.json`
    - `task_packet.schema.json`
    - `workflow_event.schema.json`
  - Schemas are produced with Pydantic v2 `model_json_schema()` using a
    consistent public title/ref naming convention.
- Add fake public fixtures:
  - one valid representative JSON fixture per public schema;
  - all fixtures use generic owners, repositories, issue numbers, URLs, command
    summaries, and repo-relative artifact refs;
  - fixtures include redaction/public-safety fields and evidence refs but no
    target-repo business data, secrets, raw logs, screenshots, private local
    paths, or real credentials.
- Update existing imports and architecture tests only as needed to preserve the
  package boundary contract from issue #5.

## Interfaces
- New Python domain modules under `hoisa.domain` become the first internal
  model interface for later application workflows, adapters, and tests.
- Public schema interface:
  - `hoisa.schemas.public.catalog.PUBLIC_SCHEMAS` or an equivalent stable
    mapping from schema file name to Pydantic model class;
  - JSON Schema artifacts under `src/hoisa/schemas/public/*.schema.json`;
  - fixture files under `tests/fixtures/public/*.json`.
- Existing interface compatibility:
  - `hoisa.domain.work_items.WorkflowStage`
  - `hoisa.domain.work_items.WorkItemRef`
  - `hoisa.ports.tracker.WorkQueue`
  - `hoisa.app.workflows.select_next_work.select_next_work`
- Dependency interface:
  - runtime dependency on Pydantic v2;
  - no database, GitHub, runner, Docker, network, or filesystem adapter
    dependency in domain modules.

## Test Plan
- Focused model tests under `tests/unit/domain/`:
  - collection roots require or generate stable IDs, timezone-aware timestamps,
    and `schema_version`;
  - naive datetimes are rejected or normalized only when the timezone is
    explicit;
  - nested value objects do not expose root identity/timestamp fields by
    inheritance;
  - gates carry exact authority, supported options, evidence refs, and decisions
    with actor/provenance and single decision timestamps;
  - workflow events require subject, actor, correlation ID, public-safety class,
    redaction status, payload schema, and evidence references where applicable;
  - task packets include bounded context, allowed actions, runner profile,
    budget, and evidence requirements.
- Public schema and fixture contract tests under `tests/unit/schemas/`:
  - every schema in the public catalog has a checked-in JSON file;
  - checked-in schema JSON matches the Pydantic-generated schema;
  - every public fixture validates with its corresponding model;
  - public fixture/schema strings are scanned for private-looking local paths,
    secrets, raw log fields, screenshot fields, and target-repo business data
    markers.
- Architecture regression tests:
  - run the existing package-boundary tests and extend them only if new modules
    require additional domain/privacy boundary checks.
- Required checks before PR:
  - `uv run python -m py_compile scripts/github/agent_workflow.py`
  - `uv run ruff check .`
  - `uv run ruff format --check .`
  - `uv run mypy scripts src tests`
  - `uv run pytest`
- Acceptance mapping:
  - model coverage acceptance is covered by domain tests and schema catalog
    membership;
  - ID/timestamp/schema-version acceptance is covered by root/value-object
    tests;
  - public-safety acceptance is covered by fixture validation and leakage scan;
  - provenance/correlation/evidence acceptance is covered by event, evidence,
    gate, and task-packet tests.

## Risks
- Risk level: treat as high for planning and review because these are
  foundational contracts for future workflow state, gates, runner records,
  evidence, persistence, and public schemas. The issue currently has a
  `risk:medium` label, but the helper classified the routed work as high risk.
- Review route: `Review Both`. This plan should receive plan review before
  human implementation approval, and implementation should receive independent
  review before the issue is considered implemented.
- Public/private safety risk: medium. Mitigate with fake fixtures, explicit
  redaction/public-safety fields, no local paths in public artifacts, and
  leakage tests.
- Over-modeling risk: medium. Mitigate by adding the smallest useful fields for
  planned workflow behavior and keeping persistence, adapters, action policy,
  and runner execution out of this slice.
- Schema-churn risk: medium. Mitigate with `schema_version`, explicit public
  schema catalog tests, and narrow field names. Later migrations remain a
  separate issue once durable storage exists.
- Adapter-coupling risk: medium. Mitigate by keeping MongoDB `_id`, BSON,
  GitHub API shapes, runner-specific logs, and local filesystem paths out of
  domain/public schemas.
- Approval gate: implementation approval authorizes only the model/schema/test
  slice described here. It does not authorize persistence implementation,
  external writes, runner execution, privileged GitHub/project mutations, or
  any private target-repo data handling.

## Simplification Check
- This issue should add contracts, fixtures, and tests. It should not add a
  service, MongoDB adapter, GitHub mapper, runner adapter, schema-generation
  CLI, migration framework, or retrospective engine.
- Prefer a small shared Pydantic base plus focused modules over a large generic
  entity framework.
- Use type-specific IDs instead of a generic database identity field in public
  models to avoid coupling the domain layer to MongoDB before persistence work.
- Keep event payloads compact and schema-named; do not create a deep event
  sourcing framework in this slice.

## Assumptions
- Pydantic v2 is acceptable as a runtime dependency for the first Hoisa package
  slice.
- Public schema artifacts may live under `src/hoisa/schemas/public/` because
  issue #5 established that package namespace for schema contracts.
- Fake fixtures can use public sample URLs and repo-relative paths, but must not
  include real local paths or private target-repo content.
- The implementation may combine or rename modules if the final structure keeps
  architecture boundaries clear and all acceptance criteria covered.

## Out Of Scope
- MongoDB repositories, indexes, migrations, transactions, or `_id` mapping.
- GitHub issue/PR/project synchronization or API DTOs.
- Runner execution, Docker integration, command execution, or log collection.
- CLI commands, service loop changes, dashboard/voice surfaces, or notification
  channels.
- External tool policy/action request implementation beyond fields needed for
  task packets or evidence references.
- Private target-repo data, local workspace paths, raw logs, screenshots, or
  secrets in public Hoisa artifacts.

## Revision History
- 2026-05-25: Initial plan scaffold.
- 2026-05-25: Filled implementation-ready plan for core workflow, gate, run,
  evidence, task-packet, and event models.
