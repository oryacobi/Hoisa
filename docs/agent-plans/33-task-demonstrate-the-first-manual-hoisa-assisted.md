---
issue: 33
title: "[Task]: Demonstrate the first manual Hoisa-assisted coding loop"
agent: Codex
branch: codex/33-task-demonstrate-the-first-manual-hoisa-assisted
created: 2026-06-21
superseded_by:
linked_pr:
---

# Plan for #33: [Task]: Demonstrate the first manual Hoisa-assisted coding loop

## Summary
- Add the smallest process-to-coding handoff layer: a pure app service that
  renders an existing `TaskPacket` into deterministic coding-runner input.
- Keep this as a manual recorded loop step. It should feed the current Docker
  Codex POC shape without adding a runner framework, scheduler, DB-backed
  service loop, or GitHub sync/write adapter.
- Preserve the process/coding boundary from epic #4: process agents decide
  task substance, authority, budget, and evidence; coding agents receive only
  the bounded packet content needed for the code task.

## Decision
- Implement a pure service under `src/hoisa/app/services/` that accepts a
  `TaskPacket` and returns a deterministic value object containing safe
  coding-runner prompt text.
- The rendered input must include only the task packet fields a coding agent
  needs: objective, workflow stage, target repo identity, context references,
  allowed actions, authority grants, runner profile, budget, and evidence
  requirements.
- The rendered input must explicitly avoid workflow-control context:
  GitHub Project state, approval mechanics, workflow-helper commands,
  repo-wide planning history, raw runner output, secrets, tokens, and local
  machine paths.
- Document the first manual loop boundary and the early fixed-logic versus
  LLM-assisted decisions in the existing architecture note.

## Implementation Approach
- Add a small service module, likely `coding_handoff.py`, with a frozen
  dataclass result such as `CodingRunnerInput` and a function such as
  `render_coding_runner_input(packet: TaskPacket)`.
- Format the prompt as stable plain text with predictable section headings so
  tests can assert the contract without depending on runner execution.
- Keep the service dependency direction app -> domain only. Do not import
  adapters, GitHub clients, the workflow helper, Docker, or persistence.
- Add focused unit tests with public-safe fake `TaskPacket` data that verify
  inclusion of required task-packet fields and exclusion of workflow-control or
  private raw-output terms.
- Update `docs/architecture/antdocs-and-development-flow.md` with a short
  manual-loop section describing process-agent responsibility, coding-agent
  responsibility, fixed logic, and LLM-assisted judgment.

## Interfaces
- New internal app API:
  - `CodingRunnerInput.prompt: str`
  - `CodingRunnerInput.task_packet_id: RecordId | None`
  - `CodingRunnerInput.work_item_id: RecordId`
  - `render_coding_runner_input(packet: TaskPacket) -> CodingRunnerInput`
- No public schema changes, no stable CLI command, and no runner port changes
  in this issue.
- Future scripts may pass `CodingRunnerInput.prompt` to
  `scripts/poc_docker_agent_run.py`, but this issue does not wire that
  execution path.

## Test Plan
- Add `tests/unit/app/test_coding_handoff.py` for the new service.
- Cover that the rendered input includes objective, workflow stage, target repo,
  context refs, allowed actions, authority grants, runner profile, budget, and
  evidence requirements.
- Cover that the rendered input excludes GitHub Project state, approval gate
  mechanics, workflow-helper commands, repo-wide planning history, raw runner
  output, secrets, tokens, and local filesystem paths.
- Run required checks before PR:
  - `uv run python -m py_compile scripts/github/agent_workflow.py`
  - `uv run ruff check .`
  - `uv run ruff format --check .`
  - `uv run mypy scripts src tests`
  - `uv run pytest`
- Local readiness evidence already gathered before implementation:
  - Docker image `hoisa-codex-poc:local` built successfully.
  - POC `codex --version` smoke inserted an `AgentRun` and private raw-result
    `WorkflowEvent`, with `raw_payload_read_back=true`.
  - Mongo contract passed using an isolated test database URI without a path.

## Risks
- Risk level: medium-to-high workflow risk. The code is pure and narrow, but it
  defines a boundary that future runner execution will rely on.
- Public/private leakage risk is mitigated by using public-safe fixtures,
  prompt text generated from `TaskPacket` summaries/refs, and no raw runner
  payload in committed docs or tests.
- Overbuilding risk is mitigated by avoiding a CLI, runner port, scheduler,
  GitHub sync/write adapter, dashboard, and broad service shell.

## Simplification Check
- Reuse the existing `TaskPacket`, `AllowedAction`, `RunnerProfile`,
  `RunBudget`, and evidence domain records.
- Keep rendering deterministic and testable rather than introducing an LLM call
  or templating framework.
- Document future execution as a manual next step instead of wiring POC Docker
  execution into this service.

## Assumptions
- Issue #31 / PR #32 satisfies the epic's first acceptance item by preserving
  Docker Codex execution plus raw-result persistence.
- This issue demonstrates the handoff contract; a later tiny task will use it
  to produce a recorded runner attempt through the POC script.
- Direct operator approval for this plan authorizes only this bounded issue
  branch and one PR.

## Revision History
- 2026-06-21: Initial plan scaffold.
- 2026-06-21: Filled implementation-ready plan from direct operator approval.
