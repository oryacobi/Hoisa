# Local MongoDB

This directory contains Hoisa's local-only MongoDB development runtime. It is
for developer-owned private orchestration state and is not a production or
cloud database path.

## Setup

From the repository root:

```bash
cd deploy/local
cp .env.example .env
```

Edit `.env` and replace the placeholder root username and password. The real
`.env` file is ignored and must not be committed, pasted into issue comments,
or copied into public logs.

Validate the Compose file without printing expanded secrets:

```bash
docker compose config --quiet
```

Start MongoDB:

```bash
docker compose up -d
docker compose ps
```

Check the database from inside the container:

```bash
docker compose exec mongodb sh -lc \
  'mongosh --quiet --username "$MONGO_INITDB_ROOT_USERNAME" --password "$MONGO_INITDB_ROOT_PASSWORD" --authenticationDatabase admin --eval "db.adminCommand({ ping: 1 })"'
```

Stop the local service without deleting data:

```bash
docker compose down
```

`docker compose down -v` deletes the local private MongoDB volume. Use it only
when intentionally discarding local Hoisa state.

## Connection Shape

Use placeholders when documenting or sharing connection strings:

```text
mongodb://<root-user>:<root-password>@127.0.0.1:27017/hoisa?authSource=admin
```

The configured root credentials are for local database initialization,
administration, and health validation only. A future Hoisa application/runtime
database user should be introduced by a separate approved adapter or schema
task.

The MongoDB image applies initialization credentials when the data directory is
empty. Changing `.env` after the volume already exists does not rotate the
stored root credentials by itself; recreate the local volume intentionally if a
throwaway development database needs new init credentials.

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

## Open Operations Questions

Backup, retention, restore, credential rotation automation, schemas, indexes,
and MongoDB application users are intentionally out of scope for this local
runtime slice.
