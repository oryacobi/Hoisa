# Contributing

Hoisa contributors and agents must follow both `AGENTS.md` and this file.
`AGENTS.md` owns workflow, safety, and agent-routing rules. This file owns
day-to-day coding standards, architecture rules, test expectations, and review
norms.

If this file conflicts with `AGENTS.md`, repo workflow skills, or a direct
operator prompt, follow the higher-priority instruction and keep the work
explicit in the plan or PR.

## Design Principles

- Prefer simplicity over backward compatibility. When old code is convoluted,
  remove or replace it with a cleaner design instead of preserving it with more
  layers, unless compatibility is an explicit requirement.
- Think in domain concepts, not implementation details. Models, parameters,
  controls, and APIs should map to things the team reasons about; fix data
  integrity at the model or storage source instead of patching it at display
  time.
- Treat corrections as structural signals. When bugs or unexpected behavior
  appear, trace the full data flow and inspect boundaries before patching the
  symptom.
- Enhance domain models instead of wrapping them. If a domain object already
  represents the concept, improve it rather than creating thin DTOs, mirrored
  views, or parallel shapes with the same fields.
- Reuse first, extract later. Extend existing mechanisms before adding helpers,
  wrappers, or layers; extract only when it creates one authoritative home for
  real shared behavior.
- Generalize at the moment of extension. When a new case mirrors an existing
  case with constants swapped, collapse the shared shape before landing; if the
  shape is not clear yet, keep the concrete duplication instead of inventing a
  speculative abstraction.
- Refactor in incremental, committable steps. Move code first and simplify
  second, keeping each step lintable, typecheckable, testable, and reviewable.
- Fix what you find. If broken or half-done code is in scope, fix it or flag it
  explicitly instead of silently working around it.

## Python Style

- Do not use `from __future__ import annotations` by default.
- Do not use `TYPE_CHECKING` to hide architectural dependencies.
- Treat type-only dependencies as real dependencies.
- Move shared concepts into `domain` or `ports` instead of creating dependency
  cycles.
- Use string forward references only for genuinely recursive or self-referential
  types, and keep them rare.
- Use modern type-hinted Python: `X | None`, built-in generics, PEP 695 generic
  syntax where appropriate, and `Self` for fluent returns.
- Type hints are mandatory on public and boundary-facing code.
- Use Pydantic for validated boundary or domain data.
- Use frozen dataclasses for ephemeral local state. Mutable dataclasses should
  be rare.
- Prefer immutable updates that return new instances over mutating shared state.
- Use sentinel defaults for tri-state boundary arguments when `None` is a valid
  explicit value.
- Use keyword-only arguments at API boundaries. Reserve positional arguments for
  short intra-module helpers.
- Prefer guard clauses and early returns over nested branches.
- Comments should explain why, not narrate what the code says.
- Treat human-readable output as a product surface: keep formatting deliberate,
  stable, and easy to scan.

## Implementation Shape

- Organize by domain noun, not generic technical buckets like `utils`,
  `helpers`, or broad `services`.
- Use deep reusable classes for shared mechanics; keep entry points, ports,
  repositories, CLIs, and workflow glue thin.
- Put behavior on the object that owns the state, lifecycle, policy, or
  invariant.
- Keep module-level helpers rare and limited to small, stateless, broadly
  reusable transformations.
- Use registries or explicit mappings for closed sets instead of scattered
  branch chains.
- Prefer composition and local `Protocol`s over inheritance for collaborator
  contracts.
- Use inheritance only for true `is-a` relationships where each layer adds one
  concrete capability.
- Prefer classmethod constructors such as `from_*`, `load_*`, `build`, or
  `empty` over free-floating factory functions.
- Keep public package surfaces curated: `__init__.py` is empty by default, and
  `__all__` exists only for deliberate public APIs.
- Retire abstractions that accumulate flags, modes, or caller-specific
  branching.

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
