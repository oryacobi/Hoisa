---
issue: 7
title: "[Task]: Extract workflow transition and selection services"
agent: Codex
branch: codex/7-task-extract-workflow-transition-and-selection-s
created: 2026-05-25
superseded_by:
linked_pr:
---

# Plan for #7: [Task]: Extract workflow transition and selection services

## Summary
- Extract the workflow state-machine and next-work selection rules from
  `scripts/github/agent_workflow.py` into testable Hoisa services.
- Keep GitHub reads, writes, Project field mutation, issue comment parsing,
  branch setup, plan publication, and PR handoff in the bootstrap helper for
  now. The extracted code should be pure policy over typed inputs and outputs.
- Add contract tests that pin the current documented behavior before the future
  service loop starts depending on it.

## Decision
- Put transition policy in the domain layer because it is core Hoisa lifecycle
  vocabulary, independent of GitHub:
  - use existing `WorkflowStage`, `QueueStatus`, and `ReviewRoute` enums from
    `src/hoisa/domain/workflow_state.py`;
  - add typed transition signals for the documented lifecycle events:
    plan posted, review ready, review changes, human approved, human requested
    changes, human requested review, and implementation complete;
  - return an intention-revealing transition result with next stage, queue
    status, next owner role, reason, and a structured event key that reuses the
    existing `WorkflowEventType` vocabulary where possible or is explicitly
    mappable to it.
- Put next-work selection policy in `src/hoisa/app/workflows/` because it
  combines domain workflow state with tracker-derived scheduling inputs such
  as phase, labels, linked PRs, issue quality shape, and worker identity.
- Keep the existing lightweight `WorkQueue`-based `select_next_work()` wrapper
  compatible if possible, and add a richer selection API alongside it rather
  than forcing tracker adapters to exist before this slice needs them.
- Update the helper to map GitHub Project items into the new typed selection
  inputs, call the new services, and then perform the same external side
  effects it performs today.

## Implementation Approach
- Add a domain transition service, most likely in
  `src/hoisa/domain/workflow_transitions.py` or as a small companion section in
  `src/hoisa/domain/workflow_state.py` if that keeps the vocabulary simpler.
  The service should expose names like:
  - `WorkflowTransitionSignal` for the event that occurred;
  - `WorkflowOwnerRole` or equivalent for `agent` versus `human`;
  - `WorkflowTransitionDecision` for next stage/status/owner/reason/event key;
  - `transition_workflow(stage, signal, review_route)` for the pure state
    machine.
- The transition service must encode every row in `docs/github-workflow.md`:
  - `Planning + plan-posted` goes to `Plan Review` for review-plan/both routes
    and `Plan Approval` otherwise;
  - `Plan Review + review-ready` goes to `Plan Approval`;
  - `Plan Review + review-changes` goes to `Planning`;
  - `Plan Approval + human-approved` goes to `Implementation`;
  - `Plan Approval + human-requested-changes` goes to `Planning`;
  - `Plan Approval + human-requested-review` goes to `Plan Review`;
  - `Implementation + implementation-complete` goes to
    `Implementation Review` for implementation-review/both routes and
    `Implemented` otherwise;
  - `Implementation Review + review-ready` goes to `Implemented`;
  - `Implementation Review + review-changes` goes to `Implementation`;
  - `Implemented + human-requested-changes` goes to `Implementation`;
  - `Implemented + human-requested-review` goes to `Implementation Review`.
- Expand or add application selection code under
  `src/hoisa/app/workflows/select_next_work.py` with typed inputs for the
  helper's current scheduling facts:
  - issue/work item number, title, body or issue type, phase, labels, project
    agent, queue status, workflow stage, review route, linked PRs, active
    blockers, and optional worker identity label;
  - selection mode values for `auto`, `plan`, `implement`, and `review`;
  - filters for issue, phase, and labels;
  - selection result with action, selected item, reason, and a structured
    selection event key.
- Preserve current selection semantics:
  - prefer in-progress work owned by this worker identity when its stage maps
    to an action allowed by the requested mode;
  - otherwise choose eligible `Todo` items in agent-owned stages only;
  - exclude human-owned stages from runnable selection;
  - exclude items with active blockers;
  - exclude planning items that already have linked PRs;
  - require task/spike issue shape for planning/review selection and task shape
    for implementation readiness checks that remain in the helper;
  - honor `agent:*` routing labels;
  - sort by phase number when available, then issue number;
  - preserve `--issue`, `--phase`, and `--label` filter behavior and reasons.
- Refactor `scripts/github/agent_workflow.py` narrowly:
  - keep `_Gh`, REST/GraphQL reads, Project field mutation, comments,
    assignees, branch/plan path setup, commits, pushes, PR creation, and
    approval comment parsing in the helper;
  - replace duplicated constants and pure helpers where practical with imports
    from the new domain/app services;
  - keep compatibility wrappers or aliases where tests and recovery commands
    still call helper internals directly;
  - avoid changing command output JSON except where new event keys can be added
    without breaking existing consumers.
- Align structured event keys with `src/hoisa/domain/events.py`:
  - prefer existing `WorkflowEventType` values for policy outcomes such as work
    selection, gate decisions, review readiness, and PR handoff;
  - when a policy-level key is more specific than the current event enum, name
    the mapping explicitly in code or tests rather than introducing an
    untraceable string.
- Update `docs/github-workflow.md` only if the implementation creates a new
  public service interface or clarifies that the helper is now an adapter over
  domain/application policy.

## Interfaces
- Domain interface:
  - `hoisa.domain.workflow_state` remains the source of stage/status/review
    route vocabulary;
  - a transition function accepts typed current stage, signal, and review route;
  - transition outputs expose next `WorkflowStage`, next `QueueStatus`, next
    owner role, reason, and structured event key aligned with or mapped to
    `WorkflowEventType`.
- Application interface:
  - a selection function accepts a sequence of typed selectable items, agent
    family, mode, identity label, and optional filters;
  - selection outputs expose a workflow action, selected item or `None`,
    reason, and structured event key aligned with or mapped to
    `WorkflowEventType`.
- Bootstrap helper interface:
  - CLI commands and JSON payloads should remain backward compatible for
    `next`, `claim`, `post-plan`, `revise-plan`, `approve`,
    `request-changes`, `request-review`, `review-ready`, `review-changes`,
    `complete`, and `active-work`;
  - helper side effects stay GitHub-specific and are not moved into domain or
    app services.
- No persistence, MongoDB, runner, service loop, or GitHub adapter interfaces
  are introduced in this issue.

## Test Plan
- Add focused domain tests, likely under
  `tests/unit/domain/test_workflow_transitions.py`, covering:
  - all documented valid transitions listed in `docs/github-workflow.md`;
  - review-route branching for plan posting and implementation handoff;
  - invalid stage/signal pairs raising a clear domain error;
  - returned owner role/status/reason/event key for human-owned and
    agent-owned next stages.
- Add focused application tests, likely under
  `tests/unit/app/test_select_next_work.py`, covering:
  - worker identity in-progress precedence;
  - mode filtering for `auto`, `plan`, `implement`, and `review`;
  - agent-owned stages versus human-owned stages;
  - active blockers;
  - planning items with linked PRs;
  - issue type/task-spike gating;
  - agent routing labels;
  - phase and issue-number ordering;
  - issue/phase/label filters and no-match reasons.
- Update helper tests in `tests/unit/github/test_agent_workflow.py` only where
  needed to cover the helper-service mapping and preserve CLI JSON behavior.
- Run before PR:
  - `uv run python -m py_compile scripts/github/agent_workflow.py`;
  - `uv run ruff check .`;
  - `uv run ruff format --check .`;
  - `uv run mypy scripts src tests`;
  - `uv run pytest`.
- Acceptance mapping:
  - stage-transition acceptance is covered by domain transition contract tests;
  - selection-preservation acceptance is covered by app selection contract tests
    plus existing helper tests;
  - intention-revealing service acceptance is covered by public function and
    result type names;
  - structured-event acceptance is covered by transition and selection result
    assertions, including checks that keys reuse or map clearly to
    `WorkflowEventType`.

## Risks
- Risk level: high. The issue touches `scripts/github/agent_workflow.py`, which
  controls queue ownership, GitHub Project state, approval routing, comments,
  and PR handoff.
- Review route: `Review Both`. This plan should receive independent plan
  review before human approval, and the implementation PR should receive
  independent implementation review before final human verification.
- Behavior regression risk: high. Mitigate by writing tests against current
  helper semantics before or alongside the extraction, then keeping the helper
  as a thin adapter.
- Adapter-coupling risk: medium. Mitigate by keeping GitHub API payloads,
  comment parsing, Project field IDs, labels API calls, and git operations out
  of domain services.
- Over-abstraction risk: medium. Mitigate by extracting only the state machine,
  selection policy, and typed policy results needed by the issue acceptance
  criteria.
- Public/private safety risk: low to medium. Use generic fixtures and avoid
  copying private target-repo content, raw logs, secrets, or local paths into
  tests or docs.
- Approval gate: approval authorizes only the extraction and tests described in
  this plan. It does not authorize privileged GitHub settings changes,
  dependency changes beyond what is already present, external writes outside
  the normal helper workflow, runner execution, persistence implementation, or
  service-loop behavior.

## Simplification Check
- Delete or reduce duplicated pure workflow helpers in
  `scripts/github/agent_workflow.py` where the new services replace them.
- Keep compatibility wrappers in the helper only when they make existing tests
  and recovery commands stable; avoid a broad rewrite of the CLI.
- Do not add a generic state-machine framework, event-sourcing framework,
  adapter registry, or persistence abstraction in this issue.
- Prefer small frozen dataclasses/enums and pure functions over service classes
  unless the existing code shape makes a class clearly simpler.
- Keep the old `WorkQueue` port usable until a later issue replaces it with a
  richer tracker adapter contract.

## Assumptions
- Issue #6's domain model slice is now on `main` and can be used as the
  vocabulary foundation.
- Comment parsing for human approval signals remains GitHub-helper behavior;
  the extracted transition service consumes the resulting typed signal.
- Implementation-readiness quality checks can remain in the helper for this
  issue as long as selection policy preserves when implementation candidates
  are surfaced.
- No external research is required because this is an internal architecture and
  behavior-preservation extraction.

## Revision History
- 2026-05-25: Initial plan published for issue #7.
- 2026-05-25: Addressed plan review note by clarifying that structured event
  keys should reuse or explicitly map to `WorkflowEventType`.
