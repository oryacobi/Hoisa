from hoisa.app.workflows.select_next_work import (
    SelectableWorkItem,
    WorkSelectionAction,
    WorkSelectionFilters,
    WorkSelectionMode,
    select_next_work_item,
)
from hoisa.domain.events import WorkflowEventType
from hoisa.domain.workflow_state import QueueStatus, WorkflowStage, WorkItemType


def test_worker_identity_in_progress_work_takes_precedence() -> None:
    result = select_next_work_item(
        (
            _item(1, stage=WorkflowStage.PLANNING),
            _item(
                9,
                status=QueueStatus.IN_PROGRESS,
                stage=WorkflowStage.IMPLEMENTATION,
                labels=("Codex-1",),
            ),
        ),
        agent="Codex",
        identity_label="Codex-1",
    )

    assert result.action == WorkSelectionAction.IMPLEMENT
    assert result.item is not None
    assert result.item.number == 9
    assert result.event_type == WorkflowEventType.WORK_ITEM_SELECTED
    assert result.event_key == WorkflowEventType.WORK_ITEM_SELECTED.value


def test_mode_filtering_selects_only_allowed_actions() -> None:
    items = (
        _item(1, stage=WorkflowStage.PLANNING),
        _item(2, stage=WorkflowStage.IMPLEMENTATION),
        _item(3, stage=WorkflowStage.PLAN_REVIEW),
    )

    implement = select_next_work_item(items, agent="Codex", mode=WorkSelectionMode.IMPLEMENT)
    plan = select_next_work_item(items, agent="Codex", mode=WorkSelectionMode.PLAN)
    review = select_next_work_item(items, agent="Codex", mode=WorkSelectionMode.REVIEW)

    assert implement.item is not None
    assert implement.item.number == 2
    assert implement.action == WorkSelectionAction.IMPLEMENT
    assert plan.item is not None
    assert plan.item.number == 1
    assert plan.action == WorkSelectionAction.PLAN
    assert review.item is not None
    assert review.item.number == 3
    assert review.action == WorkSelectionAction.REVIEW_PLAN


def test_human_owned_stages_are_not_agent_selectable() -> None:
    result = select_next_work_item(
        (
            _item(1, stage=WorkflowStage.PLAN_APPROVAL),
            _item(2, stage=WorkflowStage.IMPLEMENTED),
        ),
        agent="Codex",
    )

    assert result.action == WorkSelectionAction.NONE
    assert result.item is None
    assert result.event_type is None


def test_active_blockers_and_planning_prs_are_excluded() -> None:
    result = select_next_work_item(
        (
            _item(1, stage=WorkflowStage.PLANNING, has_active_blockers=True),
            _item(2, stage=WorkflowStage.PLANNING, linked_pull_requests=("https://pr",)),
            _item(3, stage=WorkflowStage.PLANNING),
        ),
        agent="Codex",
    )

    assert result.item is not None
    assert result.item.number == 3


def test_issue_shape_and_agent_routing_labels_gate_selection() -> None:
    result = select_next_work_item(
        (
            _item(1, stage=WorkflowStage.PLANNING, issue_type="unknown"),
            _item(2, stage=WorkflowStage.PLANNING, labels=("agent:claude",)),
            _item(3, stage=WorkflowStage.PLANNING, issue_type=WorkItemType.SPIKE),
            _item(4, stage=WorkflowStage.PLANNING, labels=("agent:codex",)),
        ),
        agent="Codex",
    )

    assert result.item is not None
    assert result.item.number == 3


def test_phase_number_then_issue_number_sorting_is_preserved() -> None:
    result = select_next_work_item(
        (
            _item(2, stage=WorkflowStage.PLANNING, phase="Phase 2"),
            _item(9, stage=WorkflowStage.PLANNING, phase="Phase 1"),
            _item(1, stage=WorkflowStage.PLANNING),
        ),
        agent="Codex",
    )

    assert result.item is not None
    assert result.item.number == 9


def test_filters_report_no_match_and_no_eligible_reasons() -> None:
    no_match = select_next_work_item(
        (_item(1, stage=WorkflowStage.PLANNING),),
        agent="Codex",
        filters=WorkSelectionFilters(issue=7),
    )
    no_eligible = select_next_work_item(
        (_item(7, stage=WorkflowStage.PLAN_APPROVAL, labels=("reviewed",)),),
        agent="Codex",
        filters=WorkSelectionFilters(issue=7, labels=("reviewed",)),
    )

    assert no_match.action == WorkSelectionAction.NONE
    assert no_match.reason == "No issue matched next filters: issue #7."
    assert no_eligible.action == WorkSelectionAction.NONE
    assert no_eligible.reason == (
        "No eligible issue matched next filters: issue #7; labels include reviewed."
    )


def _item(
    number: int,
    *,
    stage: WorkflowStage,
    status: QueueStatus = QueueStatus.TODO,
    issue_type: WorkItemType | str = WorkItemType.TASK,
    labels: tuple[str, ...] = (),
    phase: str = "",
    linked_pull_requests: tuple[str, ...] = (),
    has_active_blockers: bool = False,
) -> SelectableWorkItem:
    return SelectableWorkItem(
        number=number,
        title=f"Issue {number}",
        status=status,
        workflow_stage=stage,
        issue_type=issue_type,
        labels=labels,
        phase=phase,
        linked_pull_requests=linked_pull_requests,
        has_active_blockers=has_active_blockers,
    )
