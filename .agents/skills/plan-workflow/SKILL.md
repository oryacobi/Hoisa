---
name: plan-workflow
description: Create or revise approval-gated Hoisa plans for GitHub issues or explicit user tasks. Use after github-issue-workflow returns plan, or when the user asks to plan next, write a plan, revise a plan, prepare work for approval, or assess issue quality before implementation.
---

# Plan Workflow

## Purpose

Use this after `github-issue-workflow` identifies planning work. The output is
a durable plan file under `docs/agent-plans/` published through the workflow
helper. Planning may change workflow artifacts only.

## Workflow

1. Use `github-issue-workflow` to resolve the issue, branch, worker identity,
   workflow stage, and review route. When default `next` returns `plan`, the
   issue is already claimed, the issue branch is checked out, and the plan file
   may already be scaffolded; do not run a separate `claim`.
2. Read the issue body, relevant comments, blockers, existing plan file, and
   relevant repo docs/skills.
3. Check the issue quality bar in `AGENTS.md`.
4. If research is needed, use current primary sources and cite links in the
   plan or tracker comment.
5. Write or revise `docs/agent-plans/<issue>-<slug>.md`.
6. Publish through the helper:
   - new plan: `scripts/github/agent_workflow.py post-plan --issue <n> --agent <Agent> --plan docs/agent-plans/<issue>-<slug>.md`
   - revision: `scripts/github/agent_workflow.py revise-plan --issue <n> --agent <Agent> --plan docs/agent-plans/<issue>-<slug>.md`

The helper commits and pushes the plan branch, posts the tracker comment with a
branch link, and transitions the workflow stage.

## Plan Shape

Make plans decision-complete and implementation-ready:

- summary and intended behavior;
- important boundaries and affected files;
- public interfaces, schemas, commands, or workflow changes;
- tests and acceptance criteria;
- simplification check: what will be deleted or simplified, what complexity is
  avoided, and any compatibility path kept with reason and removal condition;
- risk classification and required approval gates;
- explicit assumptions and out-of-scope items;
- revision history.

## Do Not

- Do not implement production code during planning.
- Do not approve or reject plans unless the user explicitly asks.
- Do not post plan comments manually when the helper can publish the plan.
- Do not stop with a local-only plan file; durable plans must be committed and
  pushed by `post-plan` or `revise-plan`.
- Do not put mutable approval state in plan front matter.
- Do not copy private target-repo content into public Hoisa plans.
