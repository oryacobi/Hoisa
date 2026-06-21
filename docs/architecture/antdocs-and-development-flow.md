# AntDocs And Development Flow

This note describes the first local process-to-coding slice in Hoisa. It is
intentionally narrower than the full runner architecture: the current work is a
reviewed POC that proves a Dockerized Codex command can produce a raw process
result, while Hoisa stores a compact run summary separately from private raw
output.

## First Slice

The process layer owns workflow context and authority. For this slice that
means it decides the task substance, approved plan, runner image, command
budget, allowed environment or mounts, and expected evidence. That context may
come from GitHub issues, Project metadata, plans, and gates, but it is reduced
before the coding runner starts.

The coding runner receives only the bounded command and local runtime inputs it
needs. The smoke path does not require the coding agent to understand GitHub
Project fields, issue queue selection, approval gate mechanics, helper
commands, or broader planning history.

The local script records two durable facts:

- `AgentRun` stores the compact run summary: runner profile, budget, agent
  identity, status, timestamps, and command summary.
- `WorkflowEvent.payload` stores the private raw process result:
  stdout, stderr, exit code, image, command, network mode, timeout, and
  timestamps.

This separation keeps review surfaces small while preserving private audit data
for local workflow history.

## Local Records

The POC uses existing Antonic-backed records:

| Record | Purpose |
| --- | --- |
| `AgentRun` | Compact summary of one disposable Docker Codex attempt. |
| `WorkflowEvent` | Append-only event linked to the run, with private raw payload. |

The raw event uses a versioned payload schema:

```text
poc.docker_agent.raw_result.v1
```

The schema name is deliberately POC-scoped. Future stable runner work can
define a durable runner result schema after the first local loop proves the
shape it needs.

## Boundary

Process-layer responsibility:

- choose or receive the approved work item;
- build a bounded task packet or command;
- decide runner profile, budget, allowed actions, and expected evidence;
- persist summaries, private raw output, and workflow events;
- transition the work item after evidence exists.

Coding-runner responsibility:

- run the supplied bounded prompt or command;
- operate only within the supplied container, mounts, network mode, and budget;
- return process output and exit metadata;
- avoid queue routing, gate decisions, tracker writes, and workflow-state
  changes.

## Manual Handoff Loop

The first manual Hoisa-assisted loop adds one narrow handoff between those
layers. A process agent or human prepares a `TaskPacket`; Hoisa renders that
packet into deterministic coding-runner input; the local Docker Codex POC can
then receive the rendered prompt as its bounded command payload.

The handoff renderer is fixed logic. It copies only task-packet fields into a
stable prompt shape:

- objective;
- workflow stage;
- target repository identity;
- context references;
- allowed actions and exact authority;
- runner profile and budget;
- expected evidence.

LLM-assisted judgment may help create or refine the upstream `TaskPacket`, such
as summarizing context, choosing concise evidence refs, or recommending allowed
actions. It should not be needed by the coding runner to reconstruct GitHub
Project state, issue routing, approval mechanics, helper commands, raw runner
payloads, or broader planning history.

After the runner returns, fixed logic should persist compact `AgentRun`
summaries and private raw-result `WorkflowEvent.payload` records. Later Hoisa
work can decide whether LLM-assisted process judgment should summarize the run,
recommend the next transition, or draft a human gate card from those durable
records.

## Not In This Slice

This POC is not the production runner abstraction. It does not add a runner
port, scheduler, always-on loop, GitHub sync, GitHub write adapter, dashboard,
notification surface, or broad tool-control engine.

It also does not make raw runner output public. Public docs, tests, plans,
issues, PRs, and support notes should use fake payloads or compact summaries,
not real auth files, tokens, private target-repo content, raw logs, or
machine-specific paths.
