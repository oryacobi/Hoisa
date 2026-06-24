# 2026-06-23 Local DB And GitHub Bootstrap

Public-safe handoff notes:

- Refreshed local MongoDB setup uses ignored private credentials in
  `deploy/local/.env`.
- Reinitialized the local MongoDB data directory for a clean developer DB.
- Added GitHub repository issue connection bootstrap for a clean DB.
- Bootstrapped records include project, target repo, source connection, issue
  cursor, GitHub tool connection, and tool policies.
- Configured read-only MongoDB MCP for Codex session DB inspection.
- Kept project-board access outside the GitHub bootstrap path.

No secrets, raw database dumps, private keys, installation tokens, or private
target-repo details belong in this changelog.
