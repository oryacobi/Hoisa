---
name: review-workflow
description: Review Hoisa plans and implementations for GitHub issues and pull requests. Use when the user asks to review next, review a plan, review an implementation, review a PR, peer review, or produce posted review feedback.
---

# Review Workflow

## Purpose

Use this to review plans on issues and implementations on PRs. Reviews should
be fresh-context work: read durable artifacts and evidence, not the implementer's
conversation transcript.

## Target Selection

1. Resolve the explicit issue, PR, branch, or "review next" target.
2. For plan review, read the issue, latest plan file, relevant comments,
   blockers, and repo instructions.
3. For implementation review, read the PR body, linked issue, approved plan,
   diff, changed files, checks, comments, and relevant docs/skills.

## Plan Review

Post or return a concise review with:

- overall judgment;
- what looks right;
- blocking changes, if any;
- non-blocking notes;
- readiness statement: ready for human approval, or revise before
  implementation.

## Implementation Review

Use code-review stance:

- findings first, ordered by severity, with file/line references where possible;
- if no findings, say that clearly;
- checks reviewed or run;
- residual risks and test gaps;
- recommendation: ready for human verification, or return to implementation.

## Do Not

- Do not approve, request changes, merge, close, or resolve threads unless the
  user explicitly asks.
- Do not review only the diff when the approved plan or issue acceptance
  criteria may change the verdict.
- Do not let the implementer's explanation replace direct evidence from files,
  checks, and durable artifacts.
