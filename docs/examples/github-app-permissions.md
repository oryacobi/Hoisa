# GitHub App Permissions For Hoisa

Hoisa's GitHub App should be installed only on the repositories Hoisa is allowed
to operate. The repository issue bootstrap needs only repository metadata and
issue reads, but the current Hoisa workflow helper is broader: it comments,
creates and updates issues, opens pull requests, submits PR reviews, updates
workflow files when explicitly approved, and pushes branches.

Do not grant project-board permissions for the repo-only bootstrap. Board field
and item reads or writes are intentionally outside this bootstrap path.

## Repository Permissions

Set these repository permissions on the GitHub App:

| Permission | Access | Why Hoisa needs it |
| --- | --- | --- |
| Metadata | Read-only | Resolve repository identity and default branch. |
| Contents | Read and write | Push branches and code through git. |
| Issues | Read and write | Read issues, create issues, post comments, manage labels, manage assignees, and read blockers. |
| Pull requests | Read and write | Create/update PRs, read PR files/diffs/reviews, submit PR reviews, and reply to review comments. |
| Checks | Read and write | Read current check state and leave room for Hoisa-owned checks. |
| Commit statuses | Read and write | Read and eventually publish status-style evidence. |
| Actions | Read and write | Read workflow state/logs and leave room to rerun or cancel workflow runs. |
| Workflows | Read and write | Allow agent changes to workflow files when explicitly approved. |

## Permissions To Remove For Repo-Only Bootstrap

Remove or leave unset any Project-related permissions:

- Repository permissions: `Repository projects` / classic Projects.
- Organization permissions: `Projects`, if present.
- Account/user permissions: `Projects`, if present.

The minimum permissions for the bootstrap validation itself are `Metadata:
read` and `Issues: read`. Keep the broader repository permissions above only
for Hoisa's existing workflow operations and future code/issue/PR actions.

## Repository Workflow Surface

These permissions cover the repository operations Hoisa should be able to
perform without project-board access:

- issue comments, progress comments, plan comments, approval comments, and PR
  handoff comments;
- issue labels, identity labels, assignees, blockers, and issue metadata;
- branch pushes through git, PR creation, PR metadata updates, PR comments, PR
  reviews, review replies, review threads, changed files, and diffs;
- check/status reads and future Hoisa-owned status evidence;
- Actions workflow reads and future rerun/cancel operations.

Do not paste GitHub App private keys, installation tokens, local manifest
contents, or real target-repo private data into public docs, issues, PRs, or
logs.
