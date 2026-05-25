---
issue: 5
title: "[Task]: Create Hoisa package skeleton and architecture contracts"
agent: Codex
branch: codex/5-task-create-hoisa-package-skeleton-and-architect
created: 2026-05-24
superseded_by:
linked_pr:
---

# Plan for #5: [Task]: Create Hoisa package skeleton and architecture contracts

## Summary
- Create the first `src/hoisa` package skeleton promised by the architecture
  direction, with explicit domain, application, port, adapter, service, CLI,
  schema, and privacy boundaries.
- Add focused architecture contract tests that make the intended dependency
  direction executable before substantial behavior lands.
- Update packaging, lint, type-check, and test configuration so the new package
  is part of normal checks from the first implementation slice.

## Decision
- Implement the smallest useful Python package shape under `src/hoisa`, keeping
  modules intentionally light:
  - `domain/` for orchestration vocabulary and invariants.
  - `app/` for workflow/application coordination.
  - `ports/` for protocols used by application/domain-facing workflows.
  - `adapters/` for infrastructure implementations, initially package shells
    and fake-safe namespaces only.
  - `service/` and `cli/` for future runtime/control surfaces.
  - `schemas/` for public schema artifacts.
  - `privacy/` for public/private classification and redaction boundaries.
- Treat `docs/agent-plans/2-architecture-persistence-direction.md` as the
  source for package names and dependency direction, but defer MongoDB, GitHub,
  runner, filesystem, and service-loop behavior to later issues.
- Use static architecture tests over source files rather than runtime import
  tricks. The tests should parse imports and fail when a lower-level package
  imports a forbidden higher-level or concrete infrastructure dependency.
- Add the package to normal tooling configuration deliberately. `pyproject.toml`
  should include `src` in Ruff and mypy scope, and pytest should discover the
  new architecture tests.

## Implementation Approach
- Add `src/hoisa/` with `__init__.py` and `py.typed`.
- Add required package directories and `__init__.py` files:
  - `src/hoisa/domain/`
  - `src/hoisa/app/`
  - `src/hoisa/app/workflows/`
  - `src/hoisa/ports/`
  - `src/hoisa/adapters/`
  - `src/hoisa/adapters/external_sources/`
  - `src/hoisa/adapters/tracker/`
  - `src/hoisa/adapters/persistence/`
  - `src/hoisa/adapters/filesystem/`
  - `src/hoisa/adapters/runner/`
  - `src/hoisa/service/`
  - `src/hoisa/cli/`
  - `src/hoisa/cli/commands/`
  - `src/hoisa/schemas/`
  - `src/hoisa/schemas/public/`
  - `src/hoisa/privacy/`
- Add minimal typed boundary modules only where they help tests express real
  constraints without committing behavior too early. Good candidates:
  - `src/hoisa/domain/work_items.py` with small value objects or enums for work
    identity/stage vocabulary if needed by application stubs.
  - `src/hoisa/ports/tracker.py`, `persistence.py`, `runner.py`,
    `filesystem.py`, `clock.py`, `notifier.py`, `source_sync.py`, and
    `external_action.py` with empty or narrowly named `Protocol` shells only if
    they are imported by app workflow stubs.
  - `src/hoisa/app/workflows/select_next_work.py` as a tiny application module
    that imports domain and port abstractions, not adapters.
- Keep adapter subpackages as importable namespaces. Do not add concrete
  `github.py`, `mongodb.py`, `codex_docker.py`, `openhands.py`, or local
  filesystem behavior in this issue unless a placeholder is needed for package
  discovery and carries no external import.
- Add `tests/unit/architecture/test_package_boundaries.py` with static checks:
  - required package directories and marker files exist;
  - modules under `src/hoisa/domain` do not import `hoisa.adapters`,
    `hoisa.service`, `hoisa.cli`, PyMongo/Motor, GitHub clients, filesystem
    adapter modules, or runner adapter modules;
  - modules under `src/hoisa/app` do not import `hoisa.adapters`,
    `hoisa.service`, or `hoisa.cli`;
  - modules under `src/hoisa/app/workflows` may import `hoisa.domain` and
    `hoisa.ports`;
  - port modules do not import adapters, service, or CLI modules;
  - adapters may import domain and ports, preserving the intended
    ports-and-adapters direction.
- Implement the static import scanner with `ast` and `pathlib`, producing clear
  assertion messages that identify the offending file and import.
- Update `pyproject.toml`:
  - `tool.ruff.src = ["scripts", "src", "tests"]`;
  - `tool.mypy.files = ["scripts", "src", "tests"]`;
  - keep `package = false` unless implementation discovers packaging needs a
    deliberate change. If package installation becomes necessary for tests, add
    the smallest explicit setuptools/hatch configuration and note it in the PR.

## Interfaces
- Public Python package namespace: `hoisa`.
- Stable first package boundary names:
  - `hoisa.domain`
  - `hoisa.app`
  - `hoisa.ports`
  - `hoisa.adapters`
  - `hoisa.service`
  - `hoisa.cli`
  - `hoisa.schemas`
  - `hoisa.privacy`
- Test interface:
  - architecture tests should be ordinary pytest tests under
    `tests/unit/architecture/`;
  - tests should not require MongoDB, GitHub credentials, network access,
    Docker, or a running service.
- Tooling interface:
  - Ruff and mypy should include `src/hoisa` during normal checks.

## Test Plan
- Run focused tests while developing:
  - `uv run pytest tests/unit/architecture`
- Run required checks before PR:
  - `uv run python -m py_compile scripts/github/agent_workflow.py`
  - `uv run ruff check .`
  - `uv run ruff format --check .`
  - `uv run mypy scripts src tests`
  - `uv run pytest`
- Acceptance mapping:
  - package skeleton acceptance is covered by required-path tests;
  - domain dependency acceptance is covered by static forbidden-import tests;
  - application workflow dependency acceptance is covered by static app import
    tests and at least one minimal app workflow module;
  - packaging/check configuration acceptance is covered by Ruff/mypy/pytest
    running against `src/hoisa`.

## Risks
- Risk level: high, matching helper issue-quality output, because the change
  establishes workflow architecture boundaries that future runner, service,
  persistence, and external-tool work will depend on.
- Public/private safety risk: low for this slice if only generic package names,
  fake-safe tests, and public architecture docs are committed. Do not add local
  paths, target-repo data, secrets, raw logs, or real external credentials.
- Overbuilding risk: medium. Mitigate by creating importable boundaries and
  tests, not concrete MongoDB, GitHub, runner, filesystem, or service behavior.
- False-confidence risk: medium. Static architecture tests should catch import
  direction drift, but they do not prove runtime behavior. Later port contract
  tests remain follow-up work.
- Tooling risk: medium. Expanding mypy/Ruff to `src` may expose strict typing
  issues in new stubs; keep stubs minimal and typed.
- Approval gate: implementation should wait for human approval of this plan.
  Review route is `Review Both`, so a plan review is expected before the human
  implementation gate.

## Simplification Check
- This issue adds structure and tests only; it should not introduce service
  lifecycle, database setup, runner execution, external writes, or schema
  generation.
- Avoid generic framework abstractions beyond Python packages, `Protocol`
  placeholders where useful, and one small static import scanner.
- Follow-up work for MongoDB, GitHub sync, task packets, gates, runners, and
  public schemas should remain separate issues with their own approval gates.

## Assumptions
- `#5` is the first implementation slice from the issue `#2` architecture task
  graph.
- Empty or near-empty package modules are acceptable when paired with contract
  tests that make the boundary intentional.
- The implementation may choose fewer placeholder modules than listed if the
  required package shape and tests still satisfy the acceptance criteria.

## Out Of Scope
- MongoDB adapter or Docker Compose infrastructure.
- GitHub adapter, source sync, project metadata migration, or helper command
  migration.
- Runner behavior, Codex Docker integration, OpenHands integration, or service
  loop behavior.
- Public JSON Schema generation beyond package directories unless a tiny
  placeholder is needed for package shape.
- Any external write action, credential handling, or private target-repo data.

## Revision History
- 2026-05-24: Initial plan scaffold.
- 2026-05-24: Filled implementation-ready plan for package skeleton and
  architecture contracts.
