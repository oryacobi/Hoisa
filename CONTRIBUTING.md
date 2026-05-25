# Contributing

Hoisa contributors and agents must follow both `AGENTS.md` and this file.
`AGENTS.md` owns workflow, safety, and agent-routing rules. This file owns
day-to-day coding standards, architecture rules, test expectations, and review
norms.

If this file conflicts with `AGENTS.md`, repo workflow skills, or a direct
operator prompt, follow the higher-priority instruction and keep the work
explicit in the plan or PR.

## Python Style

- Do not use `from __future__ import annotations` by default.
- Do not use `TYPE_CHECKING` to hide architectural dependencies.
- Treat type-only dependencies as real dependencies.
- Move shared concepts into `domain` or `ports` instead of creating dependency
  cycles.
- Use string forward references only for genuinely recursive or self-referential
  types, and keep them rare.

## Architecture Boundaries

- Domain code must not depend on adapters, service, CLI, external clients, or
  infrastructure packages.
- Application code should depend on domain types and ports, not concrete
  adapters.
- Ports define boundaries; adapters implement them.
- Public Hoisa artifacts must use generic examples and must not include private
  target-repo content, local paths, secrets, raw logs, or business-specific
  plans.

## Checks

Run the relevant focused tests while developing, then run the required checks
listed in `AGENTS.md` before opening or updating a PR.
