#!/usr/bin/env python3
"""Bootstrap a private GitHub repository issue connection into a Hoisa database."""

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
from hoisa.app.services.github_connection_bootstrap import (  # noqa: E402
    GitHubBootstrapResult,
    GitHubRepoBootstrapClient,
    bootstrap_github_repo_connection,
)
from hoisa.ports.persistence import PersistenceStore  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    """Run the GitHub connection bootstrap command."""

    args = _parser().parse_args(argv)
    result = asyncio.run(_run(args))
    print(json.dumps(result.redacted_summary(), indent=2, sort_keys=True))
    return 0


async def _run(
    args: argparse.Namespace,
    *,
    client: GitHubRepoBootstrapClient | None = None,
    store: PersistenceStore | None = None,
) -> GitHubBootstrapResult:
    manifest_path = args.config.resolve()
    manifest = load_github_bootstrap_manifest(manifest_path)
    if client is None:
        resolver = LocalGitHubAppCredentialResolver.from_manifest_file(manifest_path)
        client = GitHubAppInstallationClient(
            credential_resolver=resolver,
            api_base_url=manifest.api_base_url,
        )

    connector: HoisaAntConnector | None = None
    if args.apply and store is None:
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
        return await bootstrap_github_repo_connection(
            request=manifest.bootstrap_request(),
            client=client,
            store=store,
            apply=args.apply,
        )
    finally:
        if connector is not None:
            await connector.close()


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Validate or apply a private GitHub repository issue manifest.",
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
        help="Persist public-safe connection records after successful validation.",
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
