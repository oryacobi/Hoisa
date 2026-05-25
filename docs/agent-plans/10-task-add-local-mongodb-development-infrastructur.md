---
issue: 10
title: "[Task]: Add local MongoDB development infrastructure"
agent: Codex
branch: codex/10-task-add-local-mongodb-development-infrastructur
created: 2026-05-25
superseded_by:
linked_pr:
---

# Plan for #10: [Task]: Add local MongoDB development infrastructure

## Summary
- Add a small local Docker Compose stack for a developer-owned MongoDB runtime
  that Hoisa can use in later durable-persistence work.
- Keep the slice limited to private local infrastructure, safe placeholder
  configuration, ignored runtime state, and documentation for operating the DB
  across multiple projects/repositories.
- Do not add a MongoDB persistence adapter, repository schema/index creation,
  application imports, or cloud/Atlas deployment path in this issue.

## Decision
- Create `deploy/local/` as the local-only development runtime area, with a
  tracked Compose file and tracked example configuration but no committed real
  credentials or database state.
- Use a single MongoDB service bound to localhost by default, backed by a
  persistent Docker volume. The implementation should pin a current MongoDB 8
  image tag instead of `latest`; prefer the image whose official documentation
  supports the init behavior used by the Compose file.
- Use placeholder values in `deploy/local/.env.example`; developers copy it to
  ignored `deploy/local/.env` for local use. Real local credentials must remain
  ignored and must not appear in issue comments, plans, fixtures, logs, or PR
  output.
- Document this as one developer-local Hoisa database that can serve multiple
  projects/repos by storing project and target-repo scope on future records,
  rather than by committing per-target-repo state into this public repository.
- Treat implementation as high risk because it touches credential handling and
  private local state boundaries. Approval grants only this local Compose/docs
  slice.

## Implementation Approach
- Add `deploy/local/docker-compose.yml` with one `mongodb` service:
  - image pinned through a safe default such as `mongo:8.0` or the equivalent
    documented MongoDB Community image selected during implementation;
  - host port binding defaulting to `127.0.0.1:${HOISA_MONGO_PORT:-27017}` so
    the service is not exposed on all interfaces by default;
  - `MONGO_INITDB_ROOT_USERNAME`, `MONGO_INITDB_ROOT_PASSWORD`, and
    `MONGO_INITDB_DATABASE` populated from local environment values;
  - a named persistent volume mounted at `/data/db`;
  - a simple healthcheck using `mongosh` and an authenticated `ping`/`hello`
    command if the selected image includes `mongosh`;
  - an optional read-only `./mongo-init:/docker-entrypoint-initdb.d` mount for
    future local init scripts, without adding collection schemas or indexes in
    this issue.
- Add `deploy/local/.env.example` containing only safe placeholders:
  - image/tag or MongoDB version;
  - local bind host and port;
  - root username/password placeholder values that are obviously not secrets;
  - default database name such as `hoisa`.
- Add `deploy/local/README.md` with:
  - setup steps: copy `.env.example` to `.env`, replace placeholder
    credentials, run `docker compose config`, start with `docker compose up -d`,
    inspect health, connect locally, and stop with `docker compose down`;
  - a clear warning that `docker compose down -v` deletes the local private DB;
  - the connection-string shape with placeholders only;
  - a clear note that root credentials are for local database initialization,
    administration, and health validation only; any future Hoisa application
    user, role, or runtime credential should be handled by a separate approved
    adapter/schema task;
  - the note that MongoDB init credentials affect first initialization of an
    empty data directory, so changing them later may require recreating the
    local volume intentionally;
  - how one local Hoisa DB can support multiple repositories later through
    `project_id`, `target_repo_id`, provider, owner/name, and privacy fields;
  - explicit public/private boundaries for data, logs, screenshots, and support
    bundles.
- Add `deploy/local/mongo-init/README.md` or a similarly harmless placeholder
  so the init directory exists without adding schema/index behavior.
- Update `.gitignore` only as needed to ensure:
  - `deploy/local/.env` remains ignored;
  - local MongoDB data, bind-mounted state, secret files, and logs under
    `deploy/local/` stay ignored;
  - tracked examples such as `.env.example` and README files remain visible.
- Avoid adding Python dependencies, PyMongo/Motor imports, application code,
  persistence ports behavior, migration tooling, or generated fixtures.

## Interfaces
- Developer command surface:
  - `cd deploy/local`
  - `cp .env.example .env`
  - `docker compose config`
  - `docker compose up -d`
  - `docker compose ps`
  - `docker compose down`
- Local network interface:
  - MongoDB listens inside Compose on port `27017`;
  - host access defaults to `127.0.0.1:27017`, with port override documented
    for developers who already run another MongoDB locally.
- Configuration files:
  - `deploy/local/docker-compose.yml`
  - `deploy/local/.env.example`
  - ignored `deploy/local/.env`
- Documentation files:
  - `deploy/local/README.md`
  - `deploy/local/mongo-init/README.md` if an init directory is introduced.
- Public repository boundary:
  - no committed database contents;
  - no committed real credentials;
  - no private target-repo identifiers, local worktree paths, raw logs, or
    screenshots.

## Test Plan
- Validate Compose and examples:
  - copy `deploy/local/.env.example` to a temporary or ignored
    `deploy/local/.env` if Compose needs the default local env file;
  - run `docker compose config` from `deploy/local`;
  - inspect generated config for localhost binding, a persistent volume, and no
    non-placeholder committed credentials.
  - if validation uses a real ignored `.env`, summarize the result without
    pasting expanded credentials, connection strings, or other secret-bearing
    Compose output into public PR text, logs, or issue comments.
- If Docker is available locally, smoke test the runtime:
  - start with `docker compose up -d`;
  - verify the MongoDB container is healthy or responds to a `mongosh`
    `hello`/`ping` command with local placeholder credentials;
  - stop with `docker compose down` without deleting the volume unless the test
    deliberately used throwaway data.
- Run `git diff --check` for whitespace and tracked-file sanity.
- Because this issue is expected to be docs/config-only, skip Python compile,
  Ruff, mypy, and pytest if no Python, generated fixtures, or tooling behavior
  changes. Explain the skip in the PR. If implementation touches Python or
  generated fixtures after all, run:
  - `uv run python -m py_compile scripts/github/agent_workflow.py`
  - `uv run ruff check .`
  - `uv run ruff format --check .`
  - `uv run mypy scripts src tests`
  - `uv run pytest`

## Risks
- Risk level: high, matching issue metadata, because local credentials and
  private orchestration data must stay out of public artifacts.
- Public/private leakage risk: mitigate with ignored real `.env`/state/log
  paths, placeholder-only examples, and docs that forbid publishing local DB
  contents or target-repo details.
- Local exposure risk: mitigate with localhost-only port binding by default and
  documentation for changing the port instead of exposing the service broadly.
- Credential lifecycle risk: MongoDB image initialization variables only apply
  to an empty data directory for the documented image behavior. Document the
  volume-reset implication instead of silently implying credentials can be
  rotated by editing `.env`.
- Overbuilding risk: mitigate by limiting this issue to local runtime files and
  docs. No adapter, indexes, schemas, migrations, backup automation, service
  loop, or app imports belong here.
- Operational ambiguity risk: docs should distinguish `docker compose down`
  from `docker compose down -v` and leave backup/retention as an open question
  for later approval-gated work.
- Approval gate: review route is `Review Both`; this plan should go through
  plan review and human approval before implementation.

## Simplification Check
- This issue adds a local runtime surface only. It should not introduce
  persistence abstractions or make MongoDB a dependency of domain/application
  code.
- Reuse Docker Compose and MongoDB image behavior instead of adding custom
  shell scripts, migration frameworks, or provisioning code.
- Keep examples fake and local. Do not create fake target-repo records unless a
  future schema/fixture task needs them.
- Keep `.gitignore` changes narrow to local runtime data and credentials.

## Assumptions
- Native blocker #5 is closed, so the package skeleton and architecture
  boundary task no longer blocks this planning work.
- Developers using this local setup have Docker Compose available; if not,
  implementation can still validate the YAML/docs and document that runtime
  smoke testing was skipped.
- A single developer-local MongoDB instance is acceptable for the first durable
  adapter path. Future records will carry project/repo scope instead of
  requiring separate databases per target repository.
- Default MongoDB port `27017` is acceptable as long as the docs show how to
  override it for local conflicts.

## Out Of Scope
- Managed MongoDB Atlas or any cloud database path.
- MongoDB persistence adapter code, PyMongo/Motor dependencies, repository
  contracts, schemas, indexes, migrations, or change streams.
- Backup, retention, restore, or credential rotation automation beyond
  documenting open questions and safe local warnings.
- Application or domain imports of MongoDB.
- Any external write action or privileged GitHub/project mutation beyond the
  workflow helper publishing this plan.

## Sources
- Hoisa architecture direction:
  `docs/agent-plans/2-architecture-persistence-direction.md`
- Hoisa vision: `docs/vision.md`
- Docker Compose environment interpolation:
  https://docs.docker.com/compose/how-tos/environment-variables/variable-interpolation/
- Docker Compose `env_file` and service configuration reference:
  https://docs.docker.com/reference/compose-file/services/
- Docker Compose secrets reference, if implementation chooses `_FILE` secrets
  instead of simple local env values:
  https://docs.docker.com/reference/compose-file/secrets/
- MongoDB Docker install and validation docs:
  https://www.mongodb.com/docs/v8.0/tutorial/install-mongodb-community-with-docker/
- Docker Official MongoDB image environment variable behavior:
  https://hub.docker.com/_/mongo

## Revision History
- 2026-05-25: Initial plan scaffold.
- 2026-05-25: Filled implementation-ready plan for local MongoDB development
  infrastructure.
- 2026-05-25: Addressed plan review notes by clarifying root credential scope
  and redacted Compose validation reporting.
