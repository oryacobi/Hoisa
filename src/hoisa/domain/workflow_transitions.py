"""Pure workflow transition policy."""

from dataclasses import dataclass
from enum import StrEnum

from hoisa.domain.workflow_event_types import WorkflowEventType
from hoisa.domain.workflow_vocabulary import QueueStatus, ReviewRoute, WorkflowStage


class WorkflowTransitionSignal(StrEnum):
    """Signals that advance the workflow state machine."""

    PLAN_POSTED = "plan-posted"
    REVIEW_READY = "review-ready"
    REVIEW_CHANGES = "review-changes"
    HUMAN_APPROVED = "human-approved"
    HUMAN_REQUESTED_CHANGES = "human-requested-changes"
    HUMAN_REQUESTED_REVIEW = "human-requested-review"
    IMPLEMENTATION_COMPLETE = "implementation-complete"


class WorkflowOwnerRole(StrEnum):
    """Role that owns the next workflow stage."""

    AGENT = "agent"
    HUMAN = "human"


@dataclass(frozen=True, slots=True)
class WorkflowTransitionDecision:
    """Decision produced by the workflow state machine."""

    workflow_stage: WorkflowStage
    status: QueueStatus
    owner: WorkflowOwnerRole
    reason: str
    event_type: WorkflowEventType
    event_key: str


class WorkflowTransitionError(ValueError):
    """Raised when a workflow signal is invalid for the current stage."""


PLAN_REVIEW_ROUTES = frozenset({ReviewRoute.REVIEW_PLAN, ReviewRoute.REVIEW_BOTH})
IMPLEMENTATION_REVIEW_ROUTES = frozenset(
    {ReviewRoute.REVIEW_IMPLEMENTATION, ReviewRoute.REVIEW_BOTH}
)


def transition_workflow(
    stage: WorkflowStage,
    signal: WorkflowTransitionSignal,
    review_route: ReviewRoute,
) -> WorkflowTransitionDecision:
    """Return the next workflow state for a stage, signal, and review route."""

    if stage == WorkflowStage.PLANNING and signal == WorkflowTransitionSignal.PLAN_POSTED:
        next_stage = (
            WorkflowStage.PLAN_REVIEW
            if review_route in PLAN_REVIEW_ROUTES
            else WorkflowStage.PLAN_APPROVAL
        )
        return _decision(
            workflow_stage=next_stage,
            owner=_owner_for_agent_stage(next_stage == WorkflowStage.PLAN_REVIEW),
            reason="Plan was posted.",
            event_type=WorkflowEventType.PLAN_CREATED,
        )

    if stage == WorkflowStage.PLAN_REVIEW:
        if signal == WorkflowTransitionSignal.REVIEW_READY:
            return _decision(
                workflow_stage=WorkflowStage.PLAN_APPROVAL,
                owner=WorkflowOwnerRole.HUMAN,
                reason="Plan review is ready for human approval.",
                event_type=WorkflowEventType.REVIEW_READY,
            )
        if signal == WorkflowTransitionSignal.REVIEW_CHANGES:
            return _decision(
                workflow_stage=WorkflowStage.PLANNING,
                owner=WorkflowOwnerRole.AGENT,
                reason="Plan review requested changes.",
                event_type=WorkflowEventType.REVIEW_CHANGES_REQUESTED,
            )

    if stage == WorkflowStage.PLAN_APPROVAL:
        if signal == WorkflowTransitionSignal.HUMAN_APPROVED:
            return _decision(
                workflow_stage=WorkflowStage.IMPLEMENTATION,
                owner=WorkflowOwnerRole.AGENT,
                reason="Plan has human approval.",
                event_type=WorkflowEventType.GATE_DECIDED,
                event_key="gate.decided.approved",
            )
        if signal == WorkflowTransitionSignal.HUMAN_REQUESTED_CHANGES:
            return _decision(
                workflow_stage=WorkflowStage.PLANNING,
                owner=WorkflowOwnerRole.AGENT,
                reason="Human approval requested plan changes.",
                event_type=WorkflowEventType.GATE_DECIDED,
                event_key="gate.decided.request_changes",
            )
        if signal == WorkflowTransitionSignal.HUMAN_REQUESTED_REVIEW:
            return _decision(
                workflow_stage=WorkflowStage.PLAN_REVIEW,
                owner=WorkflowOwnerRole.AGENT,
                reason="Human approval requested agent plan review.",
                event_type=WorkflowEventType.GATE_DECIDED,
                event_key="gate.decided.request_review",
            )

    if (
        stage == WorkflowStage.IMPLEMENTATION
        and signal == WorkflowTransitionSignal.IMPLEMENTATION_COMPLETE
    ):
        next_stage = (
            WorkflowStage.IMPLEMENTATION_REVIEW
            if review_route in IMPLEMENTATION_REVIEW_ROUTES
            else WorkflowStage.IMPLEMENTED
        )
        return _decision(
            workflow_stage=next_stage,
            owner=_owner_for_agent_stage(next_stage == WorkflowStage.IMPLEMENTATION_REVIEW),
            reason="Implementation was handed off.",
            event_type=WorkflowEventType.PR_OPENED,
        )

    if stage == WorkflowStage.IMPLEMENTATION_REVIEW:
        if signal == WorkflowTransitionSignal.REVIEW_READY:
            return _decision(
                workflow_stage=WorkflowStage.IMPLEMENTED,
                owner=WorkflowOwnerRole.HUMAN,
                reason="Implementation review is ready for human verification.",
                event_type=WorkflowEventType.REVIEW_READY,
            )
        if signal == WorkflowTransitionSignal.REVIEW_CHANGES:
            return _decision(
                workflow_stage=WorkflowStage.IMPLEMENTATION,
                owner=WorkflowOwnerRole.AGENT,
                reason="Implementation review requested changes.",
                event_type=WorkflowEventType.REVIEW_CHANGES_REQUESTED,
            )

    if stage == WorkflowStage.IMPLEMENTED:
        if signal == WorkflowTransitionSignal.HUMAN_REQUESTED_CHANGES:
            return _decision(
                workflow_stage=WorkflowStage.IMPLEMENTATION,
                owner=WorkflowOwnerRole.AGENT,
                reason="Human verification requested implementation changes.",
                event_type=WorkflowEventType.GATE_DECIDED,
                event_key="gate.decided.request_changes",
            )
        if signal == WorkflowTransitionSignal.HUMAN_REQUESTED_REVIEW:
            return _decision(
                workflow_stage=WorkflowStage.IMPLEMENTATION_REVIEW,
                owner=WorkflowOwnerRole.AGENT,
                reason="Human verification requested implementation review.",
                event_type=WorkflowEventType.GATE_DECIDED,
                event_key="gate.decided.request_review",
            )

    raise WorkflowTransitionError(f"Invalid workflow transition: {stage!r} + {signal!r}")


def _decision(
    *,
    workflow_stage: WorkflowStage,
    owner: WorkflowOwnerRole,
    reason: str,
    event_type: WorkflowEventType,
    event_key: str | None = None,
) -> WorkflowTransitionDecision:
    return WorkflowTransitionDecision(
        workflow_stage=workflow_stage,
        status=QueueStatus.TODO,
        owner=owner,
        reason=reason,
        event_type=event_type,
        event_key=event_key or event_type.value,
    )


def _owner_for_agent_stage(agent_owned: bool) -> WorkflowOwnerRole:
    return WorkflowOwnerRole.AGENT if agent_owned else WorkflowOwnerRole.HUMAN
