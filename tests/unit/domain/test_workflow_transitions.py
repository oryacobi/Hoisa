import pytest

from hoisa.domain.events import WorkflowEventType
from hoisa.domain.workflow_state import QueueStatus, ReviewRoute, WorkflowStage
from hoisa.domain.workflow_transitions import (
    WorkflowOwnerRole,
    WorkflowTransitionError,
    WorkflowTransitionSignal,
    transition_workflow,
)


@pytest.mark.parametrize(
    (
        "stage",
        "signal",
        "review_route",
        "next_stage",
        "owner",
        "event_type",
        "event_key",
    ),
    (
        (
            WorkflowStage.PLANNING,
            WorkflowTransitionSignal.PLAN_POSTED,
            ReviewRoute.HUMAN_ONLY,
            WorkflowStage.PLAN_APPROVAL,
            WorkflowOwnerRole.HUMAN,
            WorkflowEventType.PLAN_CREATED,
            "plan.created",
        ),
        (
            WorkflowStage.PLANNING,
            WorkflowTransitionSignal.PLAN_POSTED,
            ReviewRoute.REVIEW_PLAN,
            WorkflowStage.PLAN_REVIEW,
            WorkflowOwnerRole.AGENT,
            WorkflowEventType.PLAN_CREATED,
            "plan.created",
        ),
        (
            WorkflowStage.PLANNING,
            WorkflowTransitionSignal.PLAN_POSTED,
            ReviewRoute.REVIEW_BOTH,
            WorkflowStage.PLAN_REVIEW,
            WorkflowOwnerRole.AGENT,
            WorkflowEventType.PLAN_CREATED,
            "plan.created",
        ),
        (
            WorkflowStage.PLAN_REVIEW,
            WorkflowTransitionSignal.REVIEW_READY,
            ReviewRoute.REVIEW_BOTH,
            WorkflowStage.PLAN_APPROVAL,
            WorkflowOwnerRole.HUMAN,
            WorkflowEventType.REVIEW_READY,
            "review.ready",
        ),
        (
            WorkflowStage.PLAN_REVIEW,
            WorkflowTransitionSignal.REVIEW_CHANGES,
            ReviewRoute.REVIEW_BOTH,
            WorkflowStage.PLANNING,
            WorkflowOwnerRole.AGENT,
            WorkflowEventType.REVIEW_CHANGES_REQUESTED,
            "review.changes_requested",
        ),
        (
            WorkflowStage.PLAN_APPROVAL,
            WorkflowTransitionSignal.HUMAN_APPROVED,
            ReviewRoute.HUMAN_ONLY,
            WorkflowStage.IMPLEMENTATION,
            WorkflowOwnerRole.AGENT,
            WorkflowEventType.GATE_DECIDED,
            "gate.decided.approved",
        ),
        (
            WorkflowStage.PLAN_APPROVAL,
            WorkflowTransitionSignal.HUMAN_REQUESTED_CHANGES,
            ReviewRoute.HUMAN_ONLY,
            WorkflowStage.PLANNING,
            WorkflowOwnerRole.AGENT,
            WorkflowEventType.GATE_DECIDED,
            "gate.decided.request_changes",
        ),
        (
            WorkflowStage.PLAN_APPROVAL,
            WorkflowTransitionSignal.HUMAN_REQUESTED_REVIEW,
            ReviewRoute.HUMAN_ONLY,
            WorkflowStage.PLAN_REVIEW,
            WorkflowOwnerRole.AGENT,
            WorkflowEventType.GATE_DECIDED,
            "gate.decided.request_review",
        ),
        (
            WorkflowStage.IMPLEMENTATION,
            WorkflowTransitionSignal.IMPLEMENTATION_COMPLETE,
            ReviewRoute.HUMAN_ONLY,
            WorkflowStage.IMPLEMENTED,
            WorkflowOwnerRole.HUMAN,
            WorkflowEventType.PR_OPENED,
            "pr.opened",
        ),
        (
            WorkflowStage.IMPLEMENTATION,
            WorkflowTransitionSignal.IMPLEMENTATION_COMPLETE,
            ReviewRoute.REVIEW_IMPLEMENTATION,
            WorkflowStage.IMPLEMENTATION_REVIEW,
            WorkflowOwnerRole.AGENT,
            WorkflowEventType.PR_OPENED,
            "pr.opened",
        ),
        (
            WorkflowStage.IMPLEMENTATION,
            WorkflowTransitionSignal.IMPLEMENTATION_COMPLETE,
            ReviewRoute.REVIEW_BOTH,
            WorkflowStage.IMPLEMENTATION_REVIEW,
            WorkflowOwnerRole.AGENT,
            WorkflowEventType.PR_OPENED,
            "pr.opened",
        ),
        (
            WorkflowStage.IMPLEMENTATION_REVIEW,
            WorkflowTransitionSignal.REVIEW_READY,
            ReviewRoute.REVIEW_BOTH,
            WorkflowStage.IMPLEMENTED,
            WorkflowOwnerRole.HUMAN,
            WorkflowEventType.REVIEW_READY,
            "review.ready",
        ),
        (
            WorkflowStage.IMPLEMENTATION_REVIEW,
            WorkflowTransitionSignal.REVIEW_CHANGES,
            ReviewRoute.REVIEW_BOTH,
            WorkflowStage.IMPLEMENTATION,
            WorkflowOwnerRole.AGENT,
            WorkflowEventType.REVIEW_CHANGES_REQUESTED,
            "review.changes_requested",
        ),
        (
            WorkflowStage.IMPLEMENTED,
            WorkflowTransitionSignal.HUMAN_REQUESTED_CHANGES,
            ReviewRoute.HUMAN_ONLY,
            WorkflowStage.IMPLEMENTATION,
            WorkflowOwnerRole.AGENT,
            WorkflowEventType.GATE_DECIDED,
            "gate.decided.request_changes",
        ),
        (
            WorkflowStage.IMPLEMENTED,
            WorkflowTransitionSignal.HUMAN_REQUESTED_REVIEW,
            ReviewRoute.HUMAN_ONLY,
            WorkflowStage.IMPLEMENTATION_REVIEW,
            WorkflowOwnerRole.AGENT,
            WorkflowEventType.GATE_DECIDED,
            "gate.decided.request_review",
        ),
    ),
)
def test_documented_workflow_transitions(
    stage: WorkflowStage,
    signal: WorkflowTransitionSignal,
    review_route: ReviewRoute,
    next_stage: WorkflowStage,
    owner: WorkflowOwnerRole,
    event_type: WorkflowEventType,
    event_key: str,
) -> None:
    decision = transition_workflow(stage, signal, review_route)

    assert decision.workflow_stage == next_stage
    assert decision.status == QueueStatus.TODO
    assert decision.owner == owner
    assert decision.reason
    assert decision.event_type == event_type
    assert decision.event_key == event_key


def test_invalid_workflow_transition_raises_clear_error() -> None:
    with pytest.raises(WorkflowTransitionError, match="Invalid workflow transition"):
        transition_workflow(
            WorkflowStage.PLANNING,
            WorkflowTransitionSignal.REVIEW_READY,
            ReviewRoute.HUMAN_ONLY,
        )
