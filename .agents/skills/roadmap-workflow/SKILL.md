---
name: roadmap-workflow
description: Plan Hoisa roadmap work, task graphs, and issue metadata. Use when the user asks to plan roadmap work, create or migrate epics/tasks, break down directives into issues, organize phases, or run scoped dry-runs before tracker writes.
---

# Roadmap Workflow

## Purpose

Use this for directive-to-task planning, roadmap organization, and tracker
metadata changes. It creates small, independently plannable issues and preserves
workflow state in tracker metadata instead of issue prose.

## Workflow

1. Read `AGENTS.md`, `docs/github-workflow.md`, existing roadmap/design docs,
   and relevant issue templates.
2. Convert human direction into candidate work items with goal, context,
   acceptance criteria, out of scope, checks, risk, and review route.
3. Prefer native tracker relationships for blockers, sub-issues, milestones,
   phases, labels, and ownership.
4. Run scoped dry-runs before bulk tracker writes.
5. Ask for human approval before creating or mutating large issue sets.

## Roadmap Shape

- One roadmap/phase issue owns a coherent outcome.
- Subtasks should be independently plannable, implementable, reviewable, and
  revertible.
- Dependencies should be native tracker relationships, not prose-only lists.
- Agent routing labels are optional hints, not ownership.
- Mutable workflow state does not belong in issue bodies.

## Do Not

- Do not perform full-roadmap migrations unless the user explicitly asks.
- Do not reset workflow state unless explicitly requested or doing a fresh
  setup.
- Do not create implementation branches or PRs for docs-only roadmap planning
  unless tracked files change.
