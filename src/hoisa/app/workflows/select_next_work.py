"""Select runnable work through domain types and ports."""

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from enum import StrEnum
import re

from hoisa.domain.work_item_refs import WorkItemRef
from hoisa.domain.workflow_event_types import WorkflowEventType
from hoisa.domain.workflow_vocabulary import QueueStatus, WorkflowStage, WorkItemType
from hoisa.ports.tracker import WorkQueue

AGENT_LABELS = frozenset({"agent:codex", "agent:claude", "agent:cursor"})
AGENT_WORKFLOW_STAGES = frozenset(
    {
        WorkflowStage.PLANNING,
        WorkflowStage.PLAN_REVIEW,
        WorkflowStage.IMPLEMENTATION,
        WorkflowStage.IMPLEMENTATION_REVIEW,
    }
)
WORK_ITEM_TYPES = frozenset({WorkItemType.TASK.value, WorkItemType.SPIKE.value})


class WorkSelectionMode(StrEnum):
    """Modes that constrain next-work selection."""

    AUTO = "auto"
    PLAN = "plan"
    IMPLEMENT = "implement"
    REVIEW = "review"


class WorkSelectionAction(StrEnum):
    """Agent action selected for a workflow item."""

    PLAN = "plan"
    REVIEW_PLAN = "review-plan"
    IMPLEMENT = "implement"
    REVIEW_IMPLEMENTATION = "review-implementation"
    NONE = "none"


@dataclass(frozen=True, slots=True)
class SelectableWorkItem:
    """Tracker-derived facts needed by next-work selection policy."""

    number: int
    title: str
    status: QueueStatus
    workflow_stage: WorkflowStage
    review_route: str = ""
    issue_type: WorkItemType | str = WorkItemType.TASK
    labels: tuple[str, ...] = ()
    agent: str = ""
    phase: str = ""
    linked_pull_requests: tuple[str, ...] = ()
    has_active_blockers: bool = False


@dataclass(frozen=True, slots=True)
class WorkSelectionFilters:
    """Optional constraints for next-work selection."""

    issue: int | None = None
    phases: tuple[str, ...] = ()
    labels: tuple[str, ...] = ()

    @property
    def active(self) -> bool:
        """Return whether any filter is configured."""

        return self.issue is not None or bool(self.phases) or bool(self.labels)

    def matches(self, item: SelectableWorkItem) -> bool:
        """Return whether a selectable item satisfies all configured filters."""

        if self.issue is not None and item.number != self.issue:
            return False
        if self.phases and item.phase.strip().lower() not in _normalized_values(self.phases):
            return False
        return not self.labels or set(self.labels).issubset(item.labels)


@dataclass(frozen=True, slots=True)
class WorkSelectionResult:
    """Selected workflow action and its structured event identity."""

    action: WorkSelectionAction
    item: SelectableWorkItem | None
    reason: str
    event_type: WorkflowEventType | None = None
    event_key: str = ""


def select_next_work_item(
    items: Sequence[SelectableWorkItem],
    *,
    agent: str,
    mode: WorkSelectionMode | str = WorkSelectionMode.AUTO,
    identity_label: str = "",
    filters: WorkSelectionFilters | None = None,
) -> WorkSelectionResult:
    """Select the next workflow item and action from typed scheduling facts."""

    mode_value = _selection_mode(mode)
    active_filters = filters or WorkSelectionFilters()
    filtered_items = [item for item in items if active_filters.matches(item)]
    if active_filters.active and not filtered_items:
        return _no_selection(f"No issue matched next filters: {_describe_filters(active_filters)}.")

    owned = _sorted_items(
        item
        for item in filtered_items
        if item.status == QueueStatus.IN_PROGRESS
        and _has_identity_label(item.labels, identity_label)
        and stage_action(item.workflow_stage) in _actions_for_mode(mode_value)
    )
    if owned:
        return _selection(
            stage_action(owned[0].workflow_stage),
            owned[0],
            "Worker identity label has active work in an agent-owned stage.",
        )

    queued = _eligible_stage_items(filtered_items, agent, mode_value)
    if queued:
        return _selection(
            stage_action(queued[0].workflow_stage),
            queued[0],
            "Selected the next queued issue for an agent-actionable workflow stage.",
        )

    reason = "No eligible issue is ready for agent workflow action."
    if active_filters.active:
        reason = f"No eligible issue matched next filters: {_describe_filters(active_filters)}."
    return _no_selection(reason)


def select_next_work(queue: WorkQueue, *, stage: WorkflowStage) -> WorkItemRef | None:
    """Return the next runnable work item for a workflow stage."""

    candidates = queue.list_runnable(stage=stage)
    return candidates[0] if candidates else None


def stage_action(stage: WorkflowStage) -> WorkSelectionAction:
    """Return the agent action associated with a workflow stage."""

    if stage == WorkflowStage.PLANNING:
        return WorkSelectionAction.PLAN
    if stage == WorkflowStage.PLAN_REVIEW:
        return WorkSelectionAction.REVIEW_PLAN
    if stage == WorkflowStage.IMPLEMENTATION:
        return WorkSelectionAction.IMPLEMENT
    if stage == WorkflowStage.IMPLEMENTATION_REVIEW:
        return WorkSelectionAction.REVIEW_IMPLEMENTATION
    return WorkSelectionAction.NONE


def _eligible_stage_items(
    items: Sequence[SelectableWorkItem],
    agent: str,
    mode: WorkSelectionMode,
) -> list[SelectableWorkItem]:
    return _sorted_items(
        item
        for item in items
        if item.status == QueueStatus.TODO
        and item.workflow_stage in AGENT_WORKFLOW_STAGES
        and stage_action(item.workflow_stage) in _actions_for_mode(mode)
        and not item.has_active_blockers
        and (item.workflow_stage != WorkflowStage.PLANNING or not item.linked_pull_requests)
        and _issue_type_value(item.issue_type) in WORK_ITEM_TYPES
        and _agent_label_allows(item.labels, agent)
    )


def _actions_for_mode(mode: WorkSelectionMode) -> frozenset[WorkSelectionAction]:
    if mode == WorkSelectionMode.PLAN:
        return frozenset({WorkSelectionAction.PLAN})
    if mode == WorkSelectionMode.IMPLEMENT:
        return frozenset({WorkSelectionAction.IMPLEMENT})
    if mode == WorkSelectionMode.REVIEW:
        return frozenset(
            {WorkSelectionAction.REVIEW_PLAN, WorkSelectionAction.REVIEW_IMPLEMENTATION}
        )
    return frozenset(
        {
            WorkSelectionAction.PLAN,
            WorkSelectionAction.REVIEW_PLAN,
            WorkSelectionAction.IMPLEMENT,
            WorkSelectionAction.REVIEW_IMPLEMENTATION,
        }
    )


def _selection_mode(mode: WorkSelectionMode | str) -> WorkSelectionMode:
    if isinstance(mode, WorkSelectionMode):
        return mode
    return WorkSelectionMode(mode)


def _selection(
    action: WorkSelectionAction,
    item: SelectableWorkItem,
    reason: str,
) -> WorkSelectionResult:
    return WorkSelectionResult(
        action=action,
        item=item,
        reason=reason,
        event_type=WorkflowEventType.WORK_ITEM_SELECTED,
        event_key=WorkflowEventType.WORK_ITEM_SELECTED.value,
    )


def _no_selection(reason: str) -> WorkSelectionResult:
    return WorkSelectionResult(
        action=WorkSelectionAction.NONE,
        item=None,
        reason=reason,
    )


def _sorted_items(items: Iterable[SelectableWorkItem]) -> list[SelectableWorkItem]:
    return sorted(items, key=lambda item: (_phase_rank(item.phase), item.number))


def _phase_rank(phase: str) -> int:
    match = re.search(r"(\d+)", phase)
    return int(match.group(1)) if match else 999


def _agent_label_allows(labels: Sequence[str], agent: str) -> bool:
    label_set = set(labels)
    explicit_agent_labels = label_set & AGENT_LABELS
    if not explicit_agent_labels:
        return True
    return f"agent:{agent.lower()}" in explicit_agent_labels


def _has_identity_label(labels: Sequence[str], identity_label: str) -> bool:
    return bool(identity_label) and identity_label in labels


def _issue_type_value(issue_type: WorkItemType | str) -> str:
    if isinstance(issue_type, WorkItemType):
        return issue_type.value
    return issue_type


def _normalized_values(values: Sequence[str]) -> set[str]:
    return {value.strip().lower() for value in values}


def _describe_filters(filters: WorkSelectionFilters) -> str:
    values: list[str] = []
    if filters.issue is not None:
        values.append(f"issue #{filters.issue}")
    if filters.phases:
        values.append(f"phase in {_comma_list(filters.phases)}")
    if filters.labels:
        values.append(f"labels include {_comma_list(filters.labels)}")
    return "; ".join(values) or "none"


def _comma_list(values: Sequence[str]) -> str:
    return ", ".join(values)
