# Vision

Hoisa is a repo-native autopilot for agent work.

It should feel less like a CLI assistant and more like an operations system for
software projects that use coding agents. The core loop keeps running until it
is explicitly stopped. It consumes agent-owned work, pauses individual items
when human judgment is needed, and continues with other eligible work.

Human interaction is not centered on the CLI. Approval and direction should
live in tracker metadata, durable artifacts, and later clean voice or UI
surfaces.

## Product Thesis

Hoisa turns a repository into an autonomous-but-governed project loop:

1. Humans provide direction.
2. Hoisa converts direction into task graphs and issue metadata.
3. Agents process eligible tasks through planning, review, implementation, and
   verification stages.
4. Human gates are represented as small structured approval objects.
5. The loop waits on gated items but keeps working elsewhere.
6. Hoisa records enough workflow history to audit and improve itself.

The human should not need to babysit the loop. The human should know when they
are needed, understand the decision quickly, make a minimal choice, and let the
loop continue.

## Communication Model

Hoisa should not depend on a terminal conversation as the primary human
interface.

Use repo-native coordination first:

- GitHub issue/project metadata.
- Pull request metadata and checks.
- Durable plan files.
- Structured gate records.
- Concise issue or PR comments that point to evidence.

Later human channels can include:

- mobile notifications;
- web dashboard;
- Slack or chat integrations;
- voice conversations while driving.

Those channels should all operate on the same gate objects and tracker state.
The channel is replaceable; the decision object is durable.

## Approval Gates

An approval gate is a small structured object, not a long conversation.

It should answer:

- What decision is needed?
- Why is the human needed now?
- What is Hoisa's recommendation?
- What is the risk?
- What evidence supports the recommendation?
- What exact authority is granted by approval?
- What are the available choices?

Example shape:

```yaml
gate_id: gate_20260524_001
gate_type: plan_approval
gate_status: waiting
issue: 12
workflow_stage: Plan Approval
risk: medium
recommendation: approve
decision_needed: Approve implementation plan for issue 12.
why_human_needed: The plan sets a workflow boundary that affects future runner behavior.
authority_granted: Implement only the approved plan in one PR.
options:
  - approve
  - request_changes
  - request_fresh_review
  - defer
evidence:
  - docs/agent-plans/12-runner-boundary.md
  - reviewer verdict
  - issue quality summary
```

Approval gates should be:

- minimal;
- explicit;
- single-use;
- metadata-backed;
- easy to render in GitHub, a web UI, chat, or voice.

Approval gates should not:

- include full logs by default;
- require the human to read the agent transcript;
- grant broad future authority;
- stop unrelated work from continuing.

## Brainstorming Versus Approval

Hoisa should separate open-ended direction from execution gates.

Brainstorming can be conversational and exploratory. It may happen through CLI,
chat, voice, issues, docs, or a planning UI.

Approval is different. Approval should be a clean, constrained interaction with
small choices. When execution is blocked, Hoisa should distill the relevant
context into one gate card rather than asking the human to reconstruct the
state from comments and logs.

## Continuous Loop

The autopilot loop should run until stopped.

High-level behavior:

```text
while not stopped:
    sync tracker state
    apply resolved human gate decisions
    reset or report expired leases
    select next runnable agent-owned item

    if runnable item exists:
        claim a lease
        build a bounded task packet
        run a fresh agent in the selected runner profile
        collect evidence
        transition workflow state
        continue

    if only human-gated work remains:
        notify humans about pending gates
        wait quietly
        continue

    wait for new work or tracker changes
```

The loop should not exit just because one item needs approval. It should pause
that item, make the human need visible, and continue processing other eligible
items.

## Metadata-First State

Hoisa should keep mutable state in tracker metadata and stable artifacts, not
chat history.

Important metadata:

- workflow stage;
- status or queue ownership;
- review route;
- risk;
- gate type;
- gate status;
- agent family;
- worker identity;
- run id;
- lease expiration;
- linked plan;
- linked PR;
- check summary;
- review summary;
- warnings.

Issue bodies should describe task substance. They should not be the source of
truth for lifecycle state.

## Runner Model

Agent runs should be disposable.

Each run should have:

- one bounded task packet;
- one workflow stage;
- one runner profile;
- one fresh worktree or sandbox;
- one budget;
- one evidence bundle.

Planner, implementer, reviewer, CI fixer, and retrospective researcher are
separate roles. High-risk review should use fresh context and durable evidence,
not the implementer's conversation.

## Workflow History

Hoisa should treat its own workflow history as a product dataset.

Each run should emit structured events:

- directive captured;
- issue created;
- task selected;
- lease claimed;
- plan created;
- review requested;
- gate created;
- gate approved;
- gate rejected;
- agent started;
- agent completed;
- checks failed;
- checks repaired;
- PR opened;
- review changes requested;
- incident recorded;
- task completed.

These events should be queryable across time. The goal is not just auditability;
it is learning which workflow choices improve outcomes.

## Retrospective Loop

Hoisa should periodically research its own history and propose improvements.

Questions to answer:

- Which tasks got stuck?
- Which gates created useful human decisions?
- Which gates were noise?
- Which review routes caught real problems?
- Which agents or runner profiles produced the most rework?
- Which task shapes were too large or too vague?
- Which issue fields predicted success or failure?
- Which skills should be updated?
- Which policies should become stricter or looser?

The output should be normal Hoisa work:

1. retrospective findings;
2. recommended workflow changes;
3. proposed issues;
4. plan/review/approval like any other change.

Hoisa should improve itself through the same governed loop it provides to other
repositories.

## First Implementation Direction

The first useful implementation should stay small:

1. Define the gate object and tracker metadata mapping.
2. Define the loop state machine for one GitHub-backed repo.
3. Add a dry-run loop that selects runnable work and reports pending gates.
4. Add durable event logging for workflow transitions.
5. Add a retrospective command that summarizes fake fixture history.

Do not start with a dashboard or voice interface. Start with durable state,
minimal gates, and an always-running loop that can be observed and improved.
