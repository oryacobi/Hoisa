---
name: plan-workflow
description: Create or revise approval-gated Hoisa plans for GitHub issues or explicit user tasks. Use after github-issue-workflow returns plan, or when the user asks to plan next, write a plan, revise a plan, prepare work for approval, or assess issue quality before implementation.
---

# Plan Workflow

## Purpose

Use this after issue routing identifies planning work. The output is a durable
plan file under `docs/agent-plans/` plus a concise tracker comment or user
summary requesting the next approval/review action. Planning may change workflow
artifacts only.

## Workflow

1. Resolve the issue/task, branch, worker identity, workflow stage, and review
   route.
2. Read the issue body, relevant comments, blockers, existing plan file, and
   relevant repo docs/skills.
3. Check the issue quality bar in `AGENTS.md`.
4. If research is needed, use current primary sources and cite links in the
   plan or tracker comment.
5. Write or revise `docs/agent-plans/<issue>-<slug>.md`.
6. Publish a short comment or handoff that links to the plan and states the
   requested next action: human approval, agent review, or clarification.

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
- Do not put mutable approval state in plan front matter.
- Do not copy private target-repo content into public Hoisa plans.
