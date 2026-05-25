---
name: implementation-pr-workflow
description: Implement approved Hoisa issues and open pull requests. Use after github-issue-workflow returns implement, or when the user asks to implement approved work, address implementation review, run checks, rebase, create a PR, or finish a handoff.
---

# Implementation PR Workflow

## Purpose

Use this after a task has passed the relevant approval gate. It owns scoped code
changes, tests, rebases, PR creation, review-feedback fixes, and final handoff.

## Workflow

1. Verify implementation is allowed:
   - workflow stage is implementation;
   - active blockers are resolved;
   - no later human signal requests changes;
   - issue quality and risk gates are satisfied.
2. Read the approved plan, acceptance criteria, relevant docs/skills, and
   current code before editing.
3. Implement only approved scope. Record adjacent work as follow-up issues.
4. Run focused checks while developing, then required checks before PR.
5. Create a PR with summary, checks, risk notes, simplification evidence, and
   linked issue.
6. Post or return a concise handoff with PR link, checks, remaining risks, and
   follow-ups.

## Review Feedback

- Read existing PR comments and unresolved review threads before changing code.
- Keep each fix traceable to the feedback cluster it addresses.
- If feedback conflicts with the approved plan, surface the conflict before
  changing behavior.

## Do Not

- Do not implement before approval gates pass.
- Do not expand scope because related cleanup is visible.
- Do not mark the issue done merely because a PR opened.
- Do not discard user or other-agent changes.
