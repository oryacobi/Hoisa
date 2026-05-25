---
issue: 8
title: "[Task]: Extract issue quality, risk, and trust evaluator"
agent: Codex
branch: codex/8-task-extract-issue-quality-risk-and-trust-evalua
created: 2026-05-25
superseded_by:
linked_pr:
---

# Plan for #8: [Task]: Extract issue quality, risk, and trust evaluator

## Summary
- Extract the issue quality, risk, and trust checks currently embedded in
  `scripts/github/agent_workflow.py` into reusable Hoisa package code.
- Keep the workflow helper's `issue-quality`, `next`, and implementation-gate
  behavior compatible by adapting helper `IssueItem` records into the new
  evaluator service.
- Add focused tests that exercise task and spike template shapes, risk
  detection, trust warnings, and public-safe structured output.

## Decision
- Implement this as an application service plus small domain-facing value
  records:
  - `src/hoisa/domain/issue_quality.py` owns stable public-safe value objects
    such as issue/comment inputs, findings, and reports.
  - `src/hoisa/app/services/issue_quality.py` owns classification, required
    section checks, risk detection, trust-warning detection, and JSON-friendly
    serialization helpers.
  - `scripts/github/agent_workflow.py` keeps its current command names and JSON
    shapes, but delegates evaluator behavior to the package service through a
    narrow adapter from helper issue/comment payloads.
- Do not add direct GitHub reads, external network behavior, approval decisions,
  or new privileged policy actions to the service. It evaluates fixture-shaped
  public inputs only and returns structured findings for callers to decide how
  to route work.

## Implementation Approach
- Add `src/hoisa/domain/issue_quality.py` with frozen, typed records:
  - `IssueQualityInput`: issue number, title, labels, body, and author
    association.
  - `IssueQualityComment`: body, optional id/source, and author association.
  - `IssueQualityFinding`: stable code, severity, message, and optional source.
  - `IssueQualityReport`: issue metadata, type, risk level, risk reasons,
    readiness booleans, missing sections, findings, trust warnings, and
    recommended next action.
- Add `src/hoisa/app/services/issue_quality.py` with pure functions:
  - `classify_issue_type(labels, body)` with label-first behavior and heading
    fallback for task/spike bodies.
  - `evaluate_issue_quality(issue, comments=())`.
  - `issue_quality_report_to_json(report)` and
    `issue_quality_summary_to_json(report)` for CLI/workflow-event payloads.
  - Private helpers for canonical Markdown headings, required-section checks,
    risk detection, trust warnings, and blocking-finding checks.
- Preserve or deliberately tighten the current behavior:
  - Task required headings: `Goal`, `Context and likely files`,
    `Acceptance criteria`, `Out of scope`, `Required checks`.
  - Spike required headings: `Question`, `Context`, `Deliverable`,
    `Out of scope`.
  - Unknown issue shapes block planning/implementation.
  - Spike issues can be planning/research ready but not implementation ready.
  - `risk:high` is high; `risk:medium` is medium unless high-risk text/path
    signals are present; `risk:low` does not suppress high-risk signals.
  - High risk covers credentials/secrets, production/live/deploy language,
    network/write-tool language, privileged GitHub/project settings,
    `scripts/github/agent_workflow.py`, and `.github/workflows/`.
  - Medium risk covers source, scripts, tests, and workflow-doc paths.
  - Docs-only work can remain low risk when no higher-risk signal is present.
  - Trust warnings remain blocking for untrusted or unknown authors when work is
    high risk or asks for consequential actions, for authority override text,
    and for quoted/fenced/comment-embedded consequential action requests.
- Update `scripts/github/agent_workflow.py`:
  - Import the new evaluator records and functions.
  - Convert helper `IssueItem` plus raw GitHub comment dicts into package
    evaluator inputs.
  - Keep existing exported helper functions where callers/tests may rely on
    them, but make them thin wrappers around the package service.
  - Remove duplicated evaluator constants/helpers from the script once covered
    by package tests.

## Interfaces
- Public package surface:
  - `hoisa.domain.issue_quality.IssueQualityInput`
  - `hoisa.domain.issue_quality.IssueQualityComment`
  - `hoisa.domain.issue_quality.IssueQualityFinding`
  - `hoisa.domain.issue_quality.IssueQualityReport`
  - `hoisa.app.services.issue_quality.classify_issue_type`
  - `hoisa.app.services.issue_quality.evaluate_issue_quality`
  - `hoisa.app.services.issue_quality.issue_quality_report_to_json`
  - `hoisa.app.services.issue_quality.issue_quality_summary_to_json`
- CLI/helper compatibility:
  - `scripts/github/agent_workflow.py issue-quality --issue <n> --json` should
    keep returning `issue`, `title`, `type`, `risk_level`, `risk_reasons`,
    `ready_for_planning`, `ready_for_implementation`, `missing_sections`,
    `recommended_next_action`, `findings`, and `trust_warnings`.
  - `next --json` should keep embedding the compact issue-quality summary under
    `issue.issue_quality`.
  - Implementation gating should continue using the same readiness semantics,
    including the helper's existing active-plan compatibility path for older
    issues with missing sections.
- Architecture boundary:
  - Domain value records must not import adapters, CLI, service, external
    clients, or infrastructure.
  - Application service may import domain value records and workflow-state
    vocabulary, but not GitHub clients or concrete adapters.

## Test Plan
- Add `tests/unit/app/test_issue_quality.py` covering:
  - Task classification from `type:task` label and from body headings.
  - Spike classification from `type:spike` label and from body headings.
  - Required task/spike sections match the public issue templates and missing
    sections create blocking findings.
  - Unknown issue shapes are not ready for planning or implementation.
  - Spike issues are ready for planning/research, not implementation.
  - Risk detection for high labels, medium labels, low/docs-only cases,
    workflow helper paths, GitHub Actions paths, source/script/test paths,
    credentials, production/deploy language, network/write-tool language, and
    privileged GitHub settings.
  - Trust warnings for untrusted authors, authority override attempts, and
    quoted/fenced/embedded consequential action requests in issue bodies and
    comments.
  - JSON and summary serialization contain only public-safe structured fields.
- Update `tests/unit/github/test_agent_workflow.py` with compatibility coverage
  that the helper adapter still exposes the expected report and summary shapes.
- Required checks before implementation PR:
  - `uv run python -m py_compile scripts/github/agent_workflow.py`
  - `uv run ruff check .`
  - `uv run ruff format --check .`
  - `uv run mypy scripts src tests`
  - `uv run pytest`

## Risks
- Risk level: high. This work changes guardrail logic that can affect whether
  agent work is considered ready and whether operator confirmation is required.
- Required gates: keep this plan under Review Both, require human approval
  before implementation, and use fresh implementation review before marking the
  issue implemented.
- Main compatibility risk: moving functions out of the helper could subtly
  change `next`, `issue-quality`, or implementation gating. Mitigation: keep
  helper wrapper names, add package-level tests for evaluator behavior, and add
  helper-level compatibility tests for command payload shapes.
- Main safety risk: the evaluator could become a policy bypass if it starts
  making approval decisions or reading GitHub directly. Mitigation: pure
  fixture-shaped inputs only, no external clients in the package service, and
  reports that describe findings rather than authorizing action.
- Public/private boundary: tests and fixtures must use generic public-safe
  examples only; no private repository content, raw logs, secrets, or local
  operator paths.

## Simplification Check
- Delete the duplicated evaluator dataclasses/constants/helpers from
  `scripts/github/agent_workflow.py` after package wrappers are in place.
- Keep a single evaluator implementation instead of parallel script and package
  logic.
- Avoid adding a database schema, tracker adapter, or YAML dependency in this
  issue. Template-coupled tests can read the public template files with stdlib
  text parsing or compare explicit required-heading constants to known template
  labels.

## Assumptions
- The existing helper JSON keys are a compatibility surface for current workflow
  commands and should remain stable.
- `RiskLevel` from `hoisa.domain.workflow_state` is the shared risk vocabulary;
  if type ergonomics are awkward, the implementation may use string literals at
  service boundaries while preserving the same values.
- This task does not need new public JSON schemas; the report structure is for
  CLI output and workflow events, not a persisted collection root yet.

## Out of Scope
- Do not change issue template wording except for a follow-up explicitly scoped
  to template policy.
- Do not create approval gates, approve implementation, or make autonomous
  policy decisions.
- Do not add direct GitHub reads to `src/hoisa`.
- Do not broaden the workflow helper beyond delegating the current quality,
  risk, and trust behavior.

## Revision History
- 2026-05-25: Initial plan scaffold.
- 2026-05-25: Filled implementation-ready plan for extracting the evaluator.
