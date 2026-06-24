#!/usr/bin/env python3
"""Synchronize GitHub repository issues into a Hoisa database."""

import argparse
import asyncio
import json
import os
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from hoisa.adapters.external_sources.github import GitHubAppInstallationClient  # noqa: E402
from hoisa.adapters.filesystem.github_credentials import (  # noqa: E402
    LocalGitHubAppCredentialResolver,
    load_github_bootstrap_manifest,
)
from hoisa.adapters.persistence.antonic import HoisaAntConnector  # noqa: E402
from hoisa.app.services.github_connection_bootstrap import GitHubBootstrapRequest  # noqa: E402
from hoisa.app.services.github_issue_sync import (  # noqa: E402
    GitHubIssueSyncResult,
    sync_github_repository_issues,
)
from hoisa.ports.persistence import PersistenceStore  # noqa: E402
from hoisa.ports.source_sync import (  # noqa: E402
    GitHubIssueSourceClient,
    GitHubIssueSyncRequest,
)


def main(argv: list[str] | None = None) -> int:
    """Run the GitHub issue sync command."""

    args = _parser().parse_args(argv)
    result = asyncio.run(_run(args))
    print(json.dumps(result.redacted_summary(), indent=2, sort_keys=True))
    return 0


async def _run(
    args: argparse.Namespace,
    *,
    client: GitHubIssueSourceClient | None = None,
    store: PersistenceStore | None = None,
) -> GitHubIssueSyncResult:
    manifest_path = args.config.resolve()
    manifest = load_github_bootstrap_manifest(manifest_path)
    if client is None:
        resolver = LocalGitHubAppCredentialResolver.from_manifest_file(manifest_path)
        client = GitHubAppInstallationClient(
            credential_resolver=resolver,
            api_base_url=manifest.api_base_url,
        )

    if not args.apply:
        return _dry_run(manifest.bootstrap_request(), client)

    connector: HoisaAntConnector | None = None
    if store is None:
        mongo_uri = args.mongo_uri or os.environ.get("MONGODB_URI")
        mongo_database = args.mongo_database or os.environ.get("MONGODB_DATABASE")
        if not mongo_uri or not mongo_database:
            raise SystemExit(
                "--apply requires --mongo-uri/--mongo-database or MONGODB_URI/MONGODB_DATABASE."
            )
        connector = HoisaAntConnector(mongo_uri, database=mongo_database)
        await connector.ensure_indexes()
        store = connector

    try:
        return await sync_github_repository_issues(
            client=client,
            store=store,
            apply=True,
        )
    finally:
        if connector is not None:
            await connector.close()


def _dry_run(
    bootstrap_request: GitHubBootstrapRequest,
    client: GitHubIssueSourceClient,
) -> GitHubIssueSyncResult:
    issues = tuple(
        client.list_repository_issues(
            GitHubIssueSyncRequest(
                credential_ref=bootstrap_request.credential_ref,
                repo_owner=bootstrap_request.repo_owner,
                repo_name=bootstrap_request.repo_name,
            )
        )
    )
    imported = tuple(issue for issue in issues if not issue.is_pull_request)
    return GitHubIssueSyncResult(
        applied=False,
        source_connections=0,
        fetched_issues=len(issues),
        imported_issues=len(imported),
        skipped_pull_requests=len(issues) - len(imported),
        cursor_value="not_applied",
        created_counts={
            "source_observations": len(imported),
            "work_items": len(imported),
            "workflow_states": len(imported),
        },
        updated_counts={},
        unchanged_counts={},
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Synchronize GitHub repository issues into Hoisa records.",
    )
    parser.add_argument(
        "--config",
        required=True,
        type=Path,
        help="Path to an ignored private GitHub bootstrap manifest JSON file.",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Persist issue observations and work records.",
    )
    parser.add_argument(
        "--mongo-uri",
        default="",
        help="MongoDB connection URI for --apply. Defaults to MONGODB_URI.",
    )
    parser.add_argument(
        "--mongo-database",
        default="",
        help="MongoDB database name for --apply. Defaults to MONGODB_DATABASE.",
    )
    return parser


if __name__ == "__main__":
    raise SystemExit(main())
