# Hoisa

Hoisa is a research-stage project for human-agent project orchestration.

The goal is not to replace coding agents. Hoisa is meant to sit one level
above them: it turns human direction into bounded work, routes that work to the
right agents, monitors progress, asks humans only for meaningful decisions, and
keeps enough evidence to steer a project without flooding either side with
context.

## Current Status

The project is in its first research pass and is being set up to develop
itself through its own agent workflow. Initial artifacts:

- [Human-Agent Project Orchestration Research](docs/research/human-agent-project-orchestration.md)
- [GitHub Agent Workflow](docs/github-workflow.md)
- [Agent Instructions](AGENTS.md)

## Public/Private Boundary

Hoisa is public. Pilot repositories may be private.

Public Hoisa artifacts should contain only generalized orchestration concepts,
schemas, policies, and code. Repo-specific business logic, private issue
history, secrets, local paths, logs, screenshots, and domain content belong in
the private target repositories, not here.
