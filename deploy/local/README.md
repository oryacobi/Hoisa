# Local MongoDB For Antonic

This directory contains Hoisa's local-only MongoDB development runtime for the
Antonic-backed model and persistence layer. It is for developer-owned private
orchestration state and is not a production or cloud database path.

## Setup

From the repository root:

```bash
cd deploy/local
cp .env.example .env
```

Edit `.env` and replace the placeholder root username and password. Keep
`MONGODB_URI` aligned with those values; Antonic reads `MONGODB_URI` and
`MONGODB_DATABASE` when Hoisa connects to this local instance. The real `.env`
file is ignored and must not be committed, pasted into issue comments, or
copied into public logs.

Validate the Compose file without printing expanded secrets:

```bash
docker compose config --quiet
```

Start MongoDB:

```bash
docker compose up -d
docker compose ps
```

MongoDB stores its local data in ignored `deploy/local/data/mongodb/`. Docker
creates the directory if it does not already exist.

Check the database from inside the container:

```bash
docker compose exec mongodb sh -lc \
  'mongosh --quiet --username "$MONGO_INITDB_ROOT_USERNAME" --password "$MONGO_INITDB_ROOT_PASSWORD" --authenticationDatabase admin --eval "db.adminCommand({ ping: 1 })"'
```

Stop the local service without deleting data:

```bash
docker compose down
```

To reset the throwaway local database, stop Compose and intentionally delete
`deploy/local/data/mongodb/`. Do not commit, paste, or share files from
`deploy/local/data/`; they are private local state.

## Clean DB Bootstrap

The current local handoff path is:

1. Create or refresh ignored private credentials in `deploy/local/.env`.
2. Stop MongoDB with `docker compose --env-file .env down` from this directory.
3. Delete the throwaway local data directory: `deploy/local/data/mongodb/`.
4. Start MongoDB again with `docker compose --env-file .env up -d`.
5. Validate the service with `docker compose --env-file .env ps`.
6. From the repository root, source `deploy/local/.env` and run:

```bash
uv run python scripts/github/bootstrap_connection.py \
  --config deploy/local/secrets/github/hoisa.json \
  --apply
```

That leaves the fresh database with repository issue source metadata and GitHub
tool-control records. It does not import issues.

## Connection Shape

Use placeholders when documenting or sharing connection strings:

```text
mongodb://<root-user>:<root-password>@127.0.0.1:27017/hoisa?authSource=admin
```

For local development, export the ignored `.env` values before running Hoisa
code that uses `AntonicPersistenceProvider`:

```bash
set -a
source deploy/local/.env
set +a
```

The configured root credentials are for local database initialization,
administration, health validation, and the current developer-local Antonic
connection only. A future Hoisa application/runtime database user can be
introduced by a separate approved hardening task.

The MongoDB image applies initialization credentials when the data directory is
empty. Changing `.env` after `deploy/local/data/mongodb/` already exists does
not rotate the stored root credentials by itself; recreate that throwaway local
data directory intentionally if a development database needs new init
credentials.

## Multi-Project Scope

This local database is intended to serve one developer's Hoisa installation
across multiple projects and repositories. Future records should carry explicit
scope instead of relying on separate public artifacts:

- `project_id`
- `target_repo_id`
- `provider`
- `owner_or_namespace`
- `repo_name`
- `privacy_class`

Public Hoisa docs, plans, fixtures, support bundles, screenshots, and issue or
PR comments must not include private database contents, real credentials, raw
logs, private target-repo identifiers, or local worktree paths.

## GitHub Repository Issue Connection Bootstrap

Private GitHub connection manifests and GitHub App private keys belong under
ignored local state:

```text
deploy/local/secrets/github/
```

Use `docs/examples/github-bootstrap-manifest.example.json` as the public-safe
shape, then create a private manifest and private key file in the ignored
directory. The manifest stores GitHub App IDs, installation IDs, repository
selectors, and an opaque `credential_ref`; the PEM file stores the GitHub App
private key. Do not commit or paste either private file.

Configure the GitHub App permissions from
`docs/examples/github-app-permissions.md`. The bootstrap path validates
repository metadata and issue reads only. Hoisa's broader workflow helper still
needs write-capable repository access for comments, issue labels and assignees,
PRs, reviews, workflow file updates, and branch pushes.

Validate GitHub access without writing DB records:

```bash
uv run python scripts/github/bootstrap_connection.py \
  --config deploy/local/secrets/github/hoisa.json
```

Seed a clean local DB with connection metadata after validation:

```bash
uv run python scripts/github/bootstrap_connection.py \
  --config deploy/local/secrets/github/hoisa.json \
  --apply
```

The command prints only a redacted summary. It stores public-safe Hoisa
connection records with opaque credential references; it does not import issues,
store tokens, store private keys, inspect project boards, or perform GitHub
mutations during bootstrap validation.

## Codex MongoDB MCP

For session-time DB inspection, Codex can load the MongoDB MCP server as
`mongodb_hoisa_local`. Keep the active MCP registration in user-level Codex
config, not in this public repo. The server should:

- run in read-only mode;
- source this repo's ignored `deploy/local/.env`;
- map `MONGODB_URI` to `MDB_MCP_CONNECTION_STRING`;
- use the official `mongodb-mcp-server` package.

Safe MCP checks for a fresh session:

- list databases and confirm `hoisa` exists;
- list collections in `hoisa`;
- read `source_connections` with a projection limited to `display_name`,
  `status`, `resource_type`, and `credential_ref`.

Do not paste connection strings, expanded environment values, raw DB documents,
or private target-repo details into public artifacts.

## Open Operations Questions

Backup, retention, restore, credential rotation automation, schemas, indexes,
and MongoDB application users are intentionally out of scope for this local
runtime slice.

## Docker Codex POC Smoke

Issue #31 adds a local-only smoke path for the first process-to-coding slice.
It builds a disposable Codex image, runs one bounded command in Docker, stores a
compact `AgentRun`, and stores raw stdout/stderr/exit metadata on the paired
private `WorkflowEvent.payload`.

Build the POC image from the repository root:

```bash
docker build -f deploy/local/codex-poc.Dockerfile -t hoisa-codex-poc:local .
```

Run a non-agent image check first if you only want to validate the local image
and MongoDB path:

```bash
uv run python scripts/poc_docker_agent_run.py \
  --image hoisa-codex-poc:local \
  --agent-command 'codex --version'
```

Run a bounded Codex agent smoke with only the context it needs. The prompt below
does not include tracker item, plan, gate, or workflow-helper context:

```bash
uv run python scripts/poc_docker_agent_run.py \
  --image hoisa-codex-poc:local \
  --agent-command 'codex exec --sandbox read-only --ask-for-approval never "Print exactly: hoisa docker codex poc"'
```

The script reads `MONGODB_URI` and `MONGODB_DATABASE` from the environment or
ignored `deploy/local/.env`. By default it prints only safe summary fields:
record ids, database name, exit code, and whether the raw payload read back
from MongoDB. Do not use `--print-raw` in public logs, issue comments, PR text,
or screenshots.

If local Codex auth is needed for an agent smoke, provide it as private ignored
local state, such as placeholder-only environment or volume examples:

```bash
uv run python scripts/poc_docker_agent_run.py \
  --image hoisa-codex-poc:local \
  --env CODEX_HOME=/codex-home \
  --volume '<private-codex-home>:/codex-home:ro' \
  --agent-command 'codex exec --sandbox read-only --ask-for-approval never "Print exactly: hoisa docker codex poc"'
```

Replace placeholders locally. Do not commit or paste real auth file paths,
tokens, config contents, or raw runner output.
