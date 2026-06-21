---
issue: 31
title: "[Task]: Turn the Docker Codex POC into the first process-to-coding slice"
agent: Codex
branch: codex/31-task-turn-the-docker-codex-poc-into-the-first-pr
created: 2026-06-21
superseded_by:
linked_pr:
---

# Plan for #31: [Task]: Turn the Docker Codex POC into the first process-to-coding slice

## Summary
- Promote the proven `codex/poc` experiment into one reviewed, explicitly
  local slice: a Dockerized Codex runner smoke path that records a compact
  `AgentRun` summary and stores raw stdout/stderr/exit metadata on the paired
  private `WorkflowEvent.payload`.
- Keep the work experimental and concrete. This is not the production runner
  port, not the always-on loop, and not a GitHub/project sync implementation.
- Document the first process-to-coding boundary: the process layer prepares a
  bounded task packet, runner profile, authority, and evidence requirements;
  the coding runner receives only the prompt/files/tool authority needed for the
  code task and does not need issue-routing, Project, gate, or helper context.

## Decision
- Use `codex/poc` as implementation evidence, but reapply or cherry-pick only
  the smallest reviewable pieces needed for this issue:
  - `scripts/poc_docker_agent_run.py` or an equivalent `poc`-named script;
  - `deploy/local/codex-poc.Dockerfile`;
  - narrow local docs updates;
  - the Antonic timezone-aware client option fix if required for reliable
    datetime round trips.
- Keep raw runner output private by design:
  - `AgentRun` stores runner profile, budget, status, timestamps, compact
    command summaries, and evidence refs;
  - `WorkflowEvent.payload` stores the raw process result under a schema such
    as `poc.docker_agent.raw_result.v1`;
  - public docs, PR text, issue comments, and tests must not paste secrets,
    auth files, raw private logs, or private target-repo content.
- Keep the runner command local and explicit. The POC script may accept image,
  command, network, env, volume, workdir, timeout, Mongo URI, and database
  options, but it should not discover GitHub workflow state or invoke the
  workflow helper.
- Treat this as high risk for workflow purposes despite the issue label showing
  `risk:medium`, because the helper classified the issue as high risk and the
  slice touches runner execution, private raw output, and workflow-helper-adjacent
  evidence.

## Implementation Approach
- Start from `main` on the issue branch and use the one-commit POC branch
  (`codex/poc`, currently commit `ab7be43`) as a source, not as an unchecked
  broad merge. Keep or adjust the POC files only where they satisfy this plan.
- Add or update `scripts/poc_docker_agent_run.py`:
  - run one shell command in a throwaway Docker container through
    `subprocess.run`;
  - capture image, command, network, timeout, exit code, stdout, stderr,
    timeout status, started timestamp, and completed timestamp in a small result
    value;
  - persist an `AgentRun` whose `command_summaries` contain only compact
    summaries, not raw stdout/stderr;
  - append a paired `WorkflowEvent` whose payload contains the raw process
    result and whose `subject`/`correlation_id` link back to the `AgentRun`;
  - read both records back from MongoDB and print a safe summary JSON containing
    ids, database name, exit code, and whether the raw payload matched;
  - keep raw stdout/stderr out of the printed summary by default, with any
    explicit raw-print option documented as private local debugging only.
- Add `deploy/local/codex-poc.Dockerfile`:
  - base it on a slim Node image suitable for the current Codex CLI;
  - install only the minimal local tooling the POC needs, such as `git`,
    `ripgrep`, `ca-certificates`, and the sandbox/runtime package used by the
    CLI;
  - pin the Codex CLI version used by the POC or make the version a documented
    build argument with a safe default;
  - keep it local-only and avoid presenting it as a production runner image.
- Update `src/hoisa/adapters/persistence/antonic.py` only if needed for this
  slice's Mongo readback:
  - default Antonic client options to timezone-aware datetime handling;
  - preserve caller-provided `client_options` by merging them with the default;
  - keep PyMongo/Antonic details inside the adapter boundary.
- Add focused tests for the script and persistence behavior:
  - test the pure result-to-payload mapping without Docker or MongoDB;
  - test that the generated `AgentRun` contains compact summaries while the
    generated `WorkflowEvent` carries raw stdout/stderr in its payload;
  - test timeout and failed-exit summarization by monkeypatching
    `subprocess.run` rather than requiring Docker in unit tests;
  - extend the Antonic contract test, gated by existing Mongo environment
    variables, to insert/read an `AgentRun` and paired raw-result
    `WorkflowEvent` and verify payload round trip and timezone-aware datetimes.
- Update local documentation:
  - add the Docker image build command and script invocation to
    `deploy/local/README.md`, using placeholder auth/volume examples only;
  - document the raw result location clearly: compact `AgentRun`, private
    `WorkflowEvent.payload`;
  - add or refine a concise architecture note, likely
    `docs/architecture/antdocs-and-development-flow.md`, explaining the
    process-layer responsibilities and coding-runner responsibilities for this
    first slice;
  - update `README.md` only if a new architecture note is added.
- Do not add a full runner port, service loop, scheduler, GitHub sync/write
  adapter, fake-runner framework, dashboard, Slack/voice/mobile surface, or
  broad tool-control expansion.

## Interfaces
- Script interface:
  - `uv run python scripts/poc_docker_agent_run.py`
  - options for `--mongodb-uri`, `--database`, `--image`, `--agent-command`,
    `--agent-id`, `--work-item-id`, `--network`, `--container-workdir`,
    repeated `--env`, repeated `--volume`, `--timeout-seconds`, and an explicit
    raw-output debugging flag if retained.
- Docker interface:
  - `docker build -f deploy/local/codex-poc.Dockerfile -t hoisa-codex-poc:local .`
  - a documented local smoke invocation using `--image hoisa-codex-poc:local`;
  - any Codex auth mount or environment example must use placeholders and must
    not expose real local paths, tokens, or auth file contents.
- Persistence interface:
  - `HoisaAntConnector` remains the adapter boundary for local MongoDB;
  - the script inserts one `AgentRun` into `agent_runs`;
  - the script appends one `WorkflowEvent` into `workflow_events`;
  - the event uses `payload_schema = "poc.docker_agent.raw_result.v1"` or a
    similarly versioned POC schema name.
- Process/coding boundary:
  - process-layer inputs: issue/task substance, approved plan, allowed actions,
    runner profile, budget, and expected evidence;
  - coding-runner inputs: the bounded task prompt/packet, repo files or mounts
    explicitly allowed by the process layer, and runner credentials explicitly
    provided for the local smoke;
  - coding-runner non-inputs: GitHub Project metadata, workflow-stage routing,
    approval gate mechanics, helper commands, issue queue selection, and
    broader planning history.

## Test Plan
- Focused unit tests:
  - result payload uses only JSON scalar values and includes image, command,
    network, timeout, exit code, stdout, stderr, timeout status, and ISO
    timestamps;
  - `AgentRun` status and command summary match success, failure, and timeout
    cases without embedding raw stdout/stderr;
  - raw-result `WorkflowEvent` links to the run id through `subject` and
    `correlation_id`, carries `PRIVATE_REFERENCE`, and stores the raw payload;
  - Docker command construction honors network, env, volume, workdir, image,
    command, and timeout arguments while tests monkeypatch `subprocess.run`.
- Antonic contract coverage:
  - extend `tests/contract/persistence/test_antonic_adapter.py` or add a nearby
    contract test that runs only when `HOISA_MONGO_TEST_URI` or `MONGODB_URI`
    is set;
  - insert/read a fake public-safe `AgentRun` plus paired private
    `WorkflowEvent`;
  - assert the event payload survives round trip and retrieved datetimes remain
    timezone-aware.
- Local smoke evidence before PR:
  - validate the local MongoDB runtime is available through the existing
    `deploy/local` instructions;
  - build the POC Codex image;
  - run the script against local MongoDB with the POC image and a bounded Codex
    command/prompt that does not include GitHub issue, Project, plan, gate, or
    helper workflow context;
  - report only safe summary fields in the PR: command shape, ids if safe,
    exit status, raw-payload readback result, and omitted-secret/auth note.
- Required checks before PR:
  - `uv run python -m py_compile scripts/github/agent_workflow.py`
  - `uv run ruff check .`
  - `uv run ruff format --check .`
  - `uv run mypy scripts src tests`
  - `uv run pytest`
- Acceptance mapping:
  - local/experimental boundary is covered by names, docs, and absence of
    runner/service-loop abstractions;
  - Docker Codex plus Mongo persistence is covered by the local smoke command;
  - raw result location is covered by docs and tests for `AgentRun` versus
    `WorkflowEvent.payload`;
  - coding-runner context separation is covered by docs and the smoke prompt;
  - out-of-scope exclusions are covered by diff review and package-boundary
    tests.

## Risks
- Risk level: high for workflow gating. Runner execution, local auth handling,
  private raw outputs, Mongo persistence, and workflow evidence all need careful
  public/private boundaries.
- Public/private leakage risk: mitigate by keeping raw output private by
  default, using fake test payloads, documenting placeholder-only auth examples,
  and omitting raw logs, real tokens, real auth files, private repo content, and
  local machine paths from public artifacts.
- External/network risk: mitigate by making network mode explicit, keeping the
  POC local-only, and documenting when the Codex smoke uses local credentials.
  Approval does not authorize production-like external side effects.
- Shell-command risk: mitigate by naming this as a local POC boundary and
  requiring explicit user-provided `--agent-command`; do not wire this into an
  unattended service or queue.
- Adapter-boundary risk: mitigate by keeping BSON/Mongo/Antonic concerns inside
  scripts and adapters, with no domain/application dependency on PyMongo driver
  details.
- Overbuilding risk: mitigate by keeping the slice to the POC command, Docker
  image, tests, and docs. No generalized runner port, scheduler, GitHub sync,
  dashboard, or tool-control engine belongs here.
- Approval gate: human approval authorizes only this experimental local slice.
  It does not authorize secrets disclosure, privileged GitHub/project settings,
  production runners, always-on automation, unrelated workflow-helper changes,
  or expansion into the broader issue #4 epic.

## Simplification Check
- Reuse existing `AgentRun`, `WorkflowEvent`, Antonic persistence helpers, and
  local MongoDB infrastructure instead of adding new persistence records or a
  second storage path.
- Keep the POC script flat and explicit. Extract helper functions only where
  they make tests straightforward; do not introduce a runner framework.
- Prefer one concise architecture note or README section over a speculative
  architecture document that promises more than this slice implements.
- Keep compatibility with future runner work by naming the payload schema and
  public/private boundary clearly, but defer stable runner/task-packet APIs to
  later approved issues.

## Assumptions
- `codex/poc` remains available as local and remote evidence while this issue is
  implemented.
- The developer running the full smoke has Docker, local MongoDB, and any
  required local Codex auth configured. If auth is unavailable, implementation
  should stop and ask before substituting a non-Codex smoke for the required
  acceptance evidence.
- The local POC may use placeholder examples for auth mounts and environment
  variables, but real auth files and tokens remain ignored private state.
- No external research is required for the plan; implementation should verify
  the exact Codex CLI invocation against the pinned image before PR.

## Out Of Scope
- Full runner port or production runner abstraction.
- GitHub sync, GitHub write adapter, Project mutation outside normal workflow
  helper operations, or tracker-source reducer work.
- DB-backed queue, lease scheduler, always-on loop, dashboard, Slack, voice,
  mobile, or notification surface.
- Fake-runner framework, broad tool-control policy engine, or generalized
  action-request execution.
- Raw private logs, secrets, auth file contents, private target-repo content,
  or machine-specific local paths in committed docs, tests, plans, comments, or
  PR text.

## Sources
- Direction issue: #4, "[Epic]: Establish the first real Hoisa-assisted coding
  loop".
- POC branch evidence: `codex/poc` at `ab7be43`, "Set tz-aware Ant connector
  options".
- Hoisa vision: `docs/vision.md`.
- Workflow rules: `AGENTS.md` and `docs/github-workflow.md`.
- Existing local MongoDB docs: `deploy/local/README.md`.

## Revision History
- 2026-06-21: Initial plan scaffold.
- 2026-06-21: Filled implementation-ready plan for the local Docker Codex plus
  Mongo raw-result persistence slice.
