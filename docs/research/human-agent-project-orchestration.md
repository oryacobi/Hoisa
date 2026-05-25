# Human-Agent Project Orchestration Research

Date: 2026-05-24

## Purpose

Hoisa explores a higher-level operating layer for software projects where
humans and coding agents work together. The target outcome is a better sweet
spot between fast agent execution and human direction: less manual orchestration,
smaller context for everyone, and better control over project direction.

The first POC should orchestrate work in a private pilot repository while
keeping this public repo free of private project content.

## Executive Takeaways

1. The market is moving quickly, but most tools optimize one slice: running
   agents, defining agent graphs, reviewing PRs, or observing traces. Fewer
   tools treat the human as a scarce decision-maker whose attention must be
   scheduled, summarized, and protected.
2. The strongest design pattern is not full autonomy. It is structured
   autonomy: small work items, explicit context packs, risk-aware approval gates,
   durable state, evidence-backed review, and clear rollback paths.
3. Human-in-the-loop should be a workflow primitive, not a final "approve"
   button. The useful gates are plan approval, ambiguity resolution, privileged
   action approval, scope expansion, failed verification, and merge readiness.
4. Context reduction is a core product feature. Agents need bounded task packets
   and curated context. Humans need compact approval cards that show goal,
   risk, proposed decision, evidence, and consequences.
5. Hoisa should be agent-agnostic. It should orchestrate existing agents through
   adapters instead of becoming another coding agent.
6. The public/private split is part of the architecture. Hoisa should store
   policy, metadata, and public schemas; target repositories should own private
   context, plans, logs, and domain-specific instructions.

## Working Definition

Hoisa is a project orchestration layer for agentic software development.

It should own:

- Intake of human directives.
- Task decomposition and issue quality checks.
- Context routing and context pack selection.
- Agent assignment, sandbox/worktree selection, and run budgets.
- Approval gate generation.
- Progress monitoring and stale-work detection.
- Evidence collection for review.
- Human handoff summaries.
- Cross-agent and cross-repo coordination state.

It should not own:

- The core code-writing loop of each agent.
- Private repo business logic.
- Final merge authority.
- Secrets or privileged target-repo actions without explicit authorization.

## Landscape

### 1. Agent Runners and Coding Agent Platforms

Examples: OpenHands, SWE-agent, Jules, GitHub cloud agents, Devin-like hosted
agents.

These systems execute software tasks: inspect repos, edit files, run commands,
and produce diffs or PRs. They are closest to "agent labor." They are necessary
execution backends but usually do not solve portfolio-level coordination across
many issues, humans, agents, and approval policies.

Relevant signals:

- OpenHands provides an open-source software agent platform plus cloud and
  enterprise surfaces with integrations, multi-user support, RBAC, and
  collaboration features.
- SWE-agent research emphasizes the "agent-computer interface": agents perform
  better when the environment gives them code navigation, editing, and test
  affordances shaped for agent use.
- Jules and GitHub cloud agents show the mainstream direction: asynchronous
  tasks, plan/diff/PR flow, concurrent sessions, GitHub issue integration, and
  mid-session steering.

Hoisa opportunity: treat these as worker engines behind a common project
control plane.

### 2. Coding-Agent Control Planes

Examples: Handler.dev, Orchestratia, crewswarm, aiagentflow, Bernstein,
Armada-like products.

These are closest to Hoisa's target area. They focus on dashboards, local
sandboxes, terminal visibility, multi-agent routing, parallel work, worktrees,
auditing, and human-in-the-loop control.

Observed patterns:

- Handler.dev focuses on local sandboxes, live terminals, environment forking,
  resource monitoring, and final approval.
- Orchestratia emphasizes CLI agent coordination across servers, live terminal
  streaming, cross-repo coordination, and contracts between agents.
- crewswarm frames the human as PM and agents as engineers, with parallel lanes,
  specialist agents, persistent sessions, and local-first execution.
- aiagentflow describes a deterministic DAG of Architect, Coder, Reviewer,
  Tester, Fixer, and Judge roles with typed contracts and gates.
- Bernstein emphasizes parallel git worktrees, tracker adapters, audit chains,
  cost guards, and supply-chain coverage.

Hoisa opportunity: focus less on terminal/session management and more on the
decision economy: what the human must decide, what can be automated, what
evidence is enough, and how project direction survives across many agent runs.

### 3. SCM-Native and Enterprise SDLC Agent Platforms

Examples: GitHub agent management, GitLab Duo Agent Platform, Atlassian Rovo
Dev, Codegen, Factory Droid.

These systems are moving agentic coding into the systems where software work is
already tracked: GitHub, GitLab, Jira, Slack, Linear, CI, and PR review.

Observed patterns:

- GitHub provides a centralized Agents tab/page for starting, monitoring,
  steering, and reviewing multiple agent sessions.
- GitLab Duo Agent Platform embeds agents and flows across the SDLC, including
  issue-to-MR, code review, CI/CD repair, security analysis, planner agents, and
  full software-development flows.
- Atlassian Rovo Dev connects planning, coding, review, Jira work items,
  Bitbucket/GitHub context, permissions, and SDLC metrics.
- Codegen triggers agents from Slack, Linear, Jira, GitHub, ClickUp, Monday, or
  APIs; runs them in sandboxes; creates PRs; monitors CI; and retries failed
  checks before escalating.
- Factory Droid positions itself as an agent-native development platform across
  CLI, web, Slack/Teams, Linear/Jira, mobile, CI, and enterprise deployments
  with hierarchical policy, telemetry, audit, hooks, and sandbox controls.

Hoisa opportunity: these platforms validate the direction but are largely
ecosystem-centered or execution-centered. Hoisa can be a neutral operating
layer: cross-repo decomposition, policy, approval cards, evidence, context
budgets, agent routing, and institutional memory across whichever execution
systems a project chooses.

### 4. General Multi-Agent Frameworks

Examples: LangGraph, CrewAI, AutoGen/AutoGen Studio, MetaGPT, Marsys, Orloj.

These provide orchestration primitives rather than a full software-project
operating model.

Useful primitives:

- LangGraph gives graph state, checkpointing, interrupt/resume, and durable
  human-in-the-loop execution.
- CrewAI combines role-based "crews" with more controlled "flows", guardrails,
  memory, knowledge, observability, and human-in-the-loop triggers.
- AutoGen Studio shows a low-code interface for specifying, debugging, and
  evaluating multi-agent workflows.
- MetaGPT turns software-company roles and SOPs into agent collaboration.
- Marsys and Orloj point toward production infrastructure: topology, policy,
  state, retries, auditability, and declarative manifests.

Hoisa opportunity: borrow the primitives but define a product-development
workflow on top: directives, tasks, plans, reviews, approval gates, and project
memory.

### 5. Spec-Driven and Issue-Driven Development

Examples: GitHub Spec Kit, MetaGPT, MAGIS, HULA, TheBotCompany.

The common lesson is that agents do better when the work is broken into
structured artifacts before code starts.

Useful patterns:

- Spec Kit uses a Spec -> Plan -> Tasks -> Implement flow and supports many
  coding agents through repo-local command files and context rules.
- MAGIS uses Manager, Repository Custodian, Developer, and QA roles for GitHub
  issue resolution.
- HULA, deployed internally at Atlassian, adds human feedback into plan and code
  generation stages; the reported benefits are faster initiation and coding for
  straightforward tasks, while code quality remains a concern.
- TheBotCompany frames continuous development as Strategy -> Execution ->
  Verification with asynchronous human oversight.

Hoisa opportunity: make the issue/task lifecycle the durable source of truth,
then create agent-ready packets and human-ready approval cards from it.

### 6. Observability, Governance, and Security

Examples: AgentOps, LangSmith, PR-Agent/Qodo Merge, OWASP Agentic Top 10,
OWASP Agentic Skills Top 10, HumanLayer's 12-factor agents.

These do not usually orchestrate coding work directly, but they identify the
operational layer Hoisa needs.

Useful patterns:

- AgentOps and LangSmith show trace capture, session waterfalls, retry/replay,
  human-in-the-loop, distributed tracing, and durable execution.
- PR-Agent/Qodo Merge shows that PR review can be automated as a separate
  agentic lane with configurable review categories and multi-provider support.
- OWASP highlights agent-specific risks: behavior hijacking, tool misuse,
  identity/privilege abuse, insecure skills, supply chain risks, and human-agent
  trust exploitation.
- 12-factor agents argues for owning prompts, context windows, control flow,
  launch/pause/resume, human contact, small focused agents, and stateless
  reducer-style execution.

Hoisa opportunity: make observability and governance first-class from the
start, not an afterthought once agents are already writing code.

## Generalized Patterns From The Pilot Repo

The private pilot repo contains several reusable patterns that should be
re-authored publicly from scratch:

- One canonical root instruction contract, with secondary agent surfaces
  delegating back to it.
- Separate workflow skills for routing, planning, implementation, review, and
  roadmap work.
- Bounded context packs that tell agents what to read first and what to skip.
- A project state machine backed by issue/project metadata.
- A distinction between agent family and exact worker/session identity.
- Plan-before-code gates where planning can change workflow artifacts only.
- Durable plan archives, with short issue comments linking to full plans.
- A simplification check in plans and PRs.
- Read-only issue quality reports before implementation.
- Trust-boundary rules: issue, PR, review, and comment text is untrusted input.
- Privileged-action gates for secrets, production-like actions, account
  mutation, privileged settings, and consequential network/write operations.
- Active-work summaries with branch, plan age, PR state, checks, blockers, and
  warnings.
- Agent readiness checks for local tools, auth, temp paths, generated-output
  ignores, agent config integrity, lockfiles, registry overrides, and hooks.
- Methodology contract tests for instruction links, workflow helpers, and
  generated path exclusions.

These ideas are public-safe when described as generic patterns. Hoisa should
not copy private prose, identifiers, paths, issue numbers, branch names, domain
terms, logs, or business logic.

## Proposed Hoisa Mental Model

### Human Directive

A directive is what the human actually cares about:

- Goal.
- Constraints.
- Desired direction.
- Risk tolerance.
- Approval preference.
- Time/cost budget.
- Target repository scope.

Hoisa should convert directives into work items, not raw agent prompts.

### Work Item

A work item is the smallest unit that can be planned, assigned, reviewed, and
rolled back.

Required shape:

- Goal.
- Context pointers.
- Acceptance criteria.
- Out of scope.
- Required checks.
- Risk class.
- Approval gates.
- Suggested agent/backend.
- Evidence requirements.

### Run

A run is one agent attempt against one work item in one bounded environment.

Required shape:

- Agent backend.
- Workspace or sandbox.
- Input packet hash.
- Start/end time.
- Status.
- Cost/token budget.
- Commands/checks run.
- Files changed.
- Produced evidence.
- Human interventions.

### Approval Gate

A gate is a decision request to a human. It should be small enough to answer
quickly but rich enough to avoid blind approval.

Gate card shape:

- Decision needed.
- Why this is being asked now.
- Recommended option.
- Alternatives.
- Risk if approved.
- Risk if rejected or deferred.
- Evidence links.
- Exact authority granted by approval.

## POC Proposal

The first POC should prove that Hoisa can coordinate a private repo without
leaking private content into this public repo.

### POC Inputs

- A target repo connection.
- A project/issue query or manually selected issue.
- A repo-local instruction/context map.
- A risk policy.
- A list of available agent backends.
- A human approval policy.

### POC Loop

1. Ingest target repo metadata and public-safe workflow configuration.
2. Classify candidate work items by readiness, risk, blockers, and context
   size.
3. Produce an agent-ready task packet.
4. Produce a human-ready gate card only when a meaningful decision is needed.
5. Dispatch or hand off to an existing coding agent.
6. Monitor progress and compact logs into status snapshots.
7. Collect evidence: plan, diff, test results, review comments, unresolved
   blockers, and risk notes.
8. Ask for human approval only at defined gates.
9. Hand back an implementation-ready PR or a blocked/failed run summary.

### First Useful Slice

Start with a read-only orchestrator:

- `hoisa inspect`: summarize target repo orchestration readiness.
- `hoisa next`: select the next candidate work item and explain why.
- `hoisa packet`: create an agent-ready task packet from a selected issue.
- `hoisa gate`: create a human approval card from a plan, diff, or risk event.
- `hoisa status`: summarize active work across agents and PRs.

No private content should be persisted in Hoisa during this slice. Target repo
adapters can read private metadata locally and emit redacted summaries.

## Approval Strategy

Ask humans for approval when one of these is true:

- The agent is about to implement after planning.
- The plan changes architecture, public APIs, data contracts, security posture,
  dependencies, or workflow policy.
- The task needs secrets, privileged settings, production-like systems, or
  irreversible external effects.
- The agent wants to expand scope beyond the approved work item.
- Verification fails but the agent proposes continuing.
- A merge or release decision is needed.
- The confidence/risk tradeoff is ambiguous.

Do not ask humans for approval for routine low-risk steps:

- Reading allowed repo files.
- Running approved local checks.
- Creating a draft plan.
- Producing a redacted summary.
- Retrying a failed check within a known budget.
- Filing follow-up work.

## Metrics

Hoisa should measure whether orchestration is actually improving outcomes:

- Human approvals per merged PR.
- Human time per approved task.
- Agent run time and wall-clock cycle time.
- Percent of work items ready without clarification.
- Context packet size per task.
- PR size and review burden.
- Test/check pass rate before human review.
- Rework rate after review.
- Blocked/stale task rate.
- Scope expansion events.
- Cost per accepted change.
- Incidents, unsafe-action blocks, and policy denials.

The key metric is not "agents wrote more code." It is "humans spent less
orchestration effort per useful, directionally-correct project outcome."

## Product Bets

1. The human should be treated as a strategic bottleneck, not a chat endpoint.
2. The orchestrator should own control flow and context shaping; agents should
   own local reasoning and code execution.
3. The source of truth should be durable project state, not conversational
   memory.
4. Smaller task packets beat huge context dumps.
5. Approval gates should grant exact authority and expire after use.
6. Observability should be summarized into decisions, not exposed as raw logs.
7. Public/private boundaries should be explicit in schemas and tests.

## Gaps Worth Owning

- Cross-repo orchestration: initiatives often require multiple repo-scoped PRs,
  dependency tracking, conflict detection, and merge sequencing.
- Unified policy: teams need one answer to who may ask which agent to do what,
  in which repo, with which tools, and under which approval gates.
- Portfolio-grade planning: most tools begin from a ticket, but humans often
  begin from a vague directive, roadmap theme, incident, or strategic change.
- Review loop orchestration: PR review, CI failures, test gaps, security notes,
  and human comments need a controller that routes repair work, limits retries,
  and escalates intelligently.
- Institutional memory: repeated review feedback should become durable project
  knowledge, not disappear into chat history or isolated PR comments.
- Vendor-neutral execution: teams will mix hosted agents, local agents, GitHub
  agents, GitLab flows, and domain-specific tools. Hoisa can own routing,
  evaluation, and policy while leaving execution pluggable.

## Risks

- Overbuilding orchestration before the POC proves where humans actually spend
  time.
- Creating another framework instead of a thin operating layer over existing
  agents.
- Letting approval gates become noisy, causing humans to rubber-stamp.
- Treating issue text as trusted instructions.
- Persisting private target-repo content in public Hoisa artifacts.
- Measuring activity instead of useful project outcomes.
- Designing around one target repo so tightly that the public system cannot
  generalize.

## Open Questions

- What is the smallest state model that can coordinate multiple agents without
  becoming a project-management clone?
- Should Hoisa start as a CLI, local dashboard, GitHub app, or all three
  backed by one local store?
- Which events require durable execution from day one, and which can be simple
  local commands in the POC?
- How should Hoisa represent "human intent" separately from generated plans?
- What redaction boundary is strong enough for public development against
  private target repos?
- Which agent backends should be first-class in the pilot?

## Recommended Next Steps

1. Write a public `docs/design/poc-architecture.md` with schemas for Directive,
   WorkItem, Run, Evidence, and ApprovalGate.
2. Define a public privacy policy for target-repo adapters.
3. Build a read-only CLI that can inspect a target repo and produce redacted
   orchestration summaries.
4. Add a fixture-based test suite that proves private-like content is not
   written into public outputs.
5. Run the first pilot on one private issue using manual dispatch, then compare
   the result against the baseline human orchestration process.

## Source Index

- Anthropic, Building Effective Agents: https://www.anthropic.com/engineering/building-effective-agents
- HumanLayer, 12 Factor Agents: https://github.com/humanlayer/12-factor-agents
- LangGraph interrupts / human-in-the-loop: https://docs.langchain.com/oss/python/langgraph/interrupts
- LangSmith core capabilities: https://docs.langchain.com/langsmith/core-capabilities
- CrewAI documentation: https://docs.crewai.com/
- AutoGen Studio paper: https://www.microsoft.com/en-us/research/uploads/prod/2024/08/AutoGen_Studio-12.pdf
- MetaGPT: https://github.com/FoundationAgents/MetaGPT
- SWE-agent paper: https://arxiv.org/abs/2405.15793
- OpenHands: https://github.com/OpenHands/OpenHands
- HULA paper: https://arxiv.org/abs/2411.12924
- MAGIS paper: https://arxiv.org/abs/2403.17927
- TheBotCompany paper: https://arxiv.org/abs/2603.25928
- GitHub Spec Kit: https://github.github.com/spec-kit/
- GitHub agent management: https://docs.github.com/en/copilot/concepts/agents/cloud-agent/agent-management
- Google Jules: https://jules.google/
- Handler.dev: https://handler.dev/
- Orchestratia: https://orchestratia.com/
- crewswarm: https://crewswarm.ai/
- aiagentflow: https://www.aiagentflow.dev/
- Bernstein: https://bernstein.run/
- Marsys: https://www.marsys.ai/
- Orloj: https://www.orloj.dev/
- AgentOps: https://docs.agentops.ai/
- PR-Agent: https://github.com/The-PR-Agent/pr-agent
- GitLab Duo Agent Platform: https://docs.gitlab.com/user/duo_agent_platform/
- Atlassian Rovo Dev: https://www.atlassian.com/software/rovo-dev
- Codegen documentation: https://docs.codegen.com/introduction/overview
- Codegen agent workflow: https://docs.codegen.com/capabilities/capabilities
- Factory: https://github.com/Factory-AI/factory
- Factory enterprise overview: https://docs.factory.ai/enterprise/index
- OWASP Top 10 for Agentic Applications release: https://genai.owasp.org/2025/12/09/owasp-genai-security-project-releases-top-10-risks-and-mitigations-for-agentic-ai-security/
- OWASP Agentic Skills Top 10: https://owasp.org/www-project-agentic-skills-top-10/
