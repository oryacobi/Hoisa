"""Select runnable work through domain types and ports."""

from hoisa.domain.work_items import WorkflowStage, WorkItemRef
from hoisa.ports.tracker import WorkQueue


def select_next_work(queue: WorkQueue, *, stage: WorkflowStage) -> WorkItemRef | None:
    """Return the next runnable work item for a workflow stage."""

    candidates = queue.list_runnable(stage=stage)
    return candidates[0] if candidates else None
