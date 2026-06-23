# Hoisa

Hoisa is a research-stage project for human-agent project orchestration.

The goal is not to replace coding agents. Hoisa is meant to sit one level
above them: it turns human direction into bounded work, routes that work to the
right agents, monitors progress, asks humans only for meaningful decisions, and
keeps enough evidence to steer a project without flooding either side with
context.

## Current Status

The project is in its first research pass and is being set up to develop
itself through its own agent workflow. The local development path can now
reinitialize MongoDB and bootstrap a GitHub repository issue connection into a
clean database.

Initial artifacts:

- [Vision](docs/vision.md)
- [Human-Agent Project Orchestration Research](docs/research/human-agent-project-orchestration.md)
- [AntDocs And Development Flow](docs/architecture/antdocs-and-development-flow.md)
- [GitHub Agent Workflow](docs/github-workflow.md)
- [Agent Instructions](AGENTS.md)

## Direction

Hoisa should become a repo-native autopilot loop. It should keep consuming
eligible agent work until stopped, pause only the items that need human
judgment, and represent approval needs as small metadata-backed gate cards
rather than long CLI conversations.

Hoisa should also record its own workflow history so it can periodically review
what worked, what got stuck, and which workflow rules should change.

## Public/Private Boundary

Hoisa is public. Pilot repositories may be private.

Public Hoisa artifacts should contain only generalized orchestration concepts,
schemas, policies, and code. Repo-specific business logic, private issue
history, secrets, local paths, logs, screenshots, and domain content belong in
the private target repositories, not here.
