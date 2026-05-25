---
name: review-workflow
description: Review Hoisa plans and implementations for GitHub issues and pull requests. Use when the user asks to review next, review a plan, review an implementation, review a PR, peer review, or produce posted review feedback.
---

# Review Workflow

## Purpose

Use this to review plans on issues and implementations on PRs. Reviews should
be fresh-context work: read durable artifacts and evidence, not the implementer's
conversation transcript. Use the workflow helper for target resolution, issue
and PR reads, comments, and review-stage transitions.

## Target Selection

1. Use `github-issue-workflow` to resolve the explicit issue, PR, branch, or
   "review next" target. For "review next", let
   `scripts/github/agent_workflow.py next --agent <Agent> --mode review --json`
   choose queued plan or implementation review work.
2. For plan review, read the issue, latest plan file, relevant comments,
   blockers, and repo instructions.
3. For implementation review, use helper commands such as `pr-view`,
   `pr-comments`, `pr-files`, `pr-diff`, and `pr-checks` to read the PR body,
   linked issue, approved plan, diff, changed files, checks, comments, and
   relevant docs/skills.

## Plan Review

Post the plan review as an issue comment through
`scripts/github/agent_workflow.py issue-comment`. Use:

- overall judgment;
- what looks right;
- blocking changes, if any;
- non-blocking notes;
- readiness statement: ready for human approval, or revise before
  implementation.

When the target is in `Workflow Stage=Plan Review`, finish with
`scripts/github/agent_workflow.py review-ready` if the plan is ready for human
approval, or `review-changes` if it needs another planning pass.

## Implementation Review

Use code-review stance:

- findings first, ordered by severity, with file/line references where possible;
- if no findings, say that clearly;
- checks reviewed or run;
- residual risks and test gaps;
- recommendation: ready for human verification, or return to implementation.

Post implementation reviews through `scripts/github/agent_workflow.py pr-comment`
or `pr-review`. When the target is in `Workflow Stage=Implementation Review`,
finish with `review-ready` if ready for human verification, or `review-changes`
if it must return to implementation.

## Do Not

- Do not approve, request changes, merge, close, or resolve threads unless the
  user explicitly asks.
- Do not use the GitHub connector for routine review comments, PR files, diffs,
  checks, or helper-supported review transitions.
- Do not review only the diff when the approved plan or issue acceptance
  criteria may change the verdict.
- Do not let the implementer's explanation replace direct evidence from files,
  checks, and durable artifacts.
