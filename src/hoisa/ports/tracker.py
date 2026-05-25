"""Tracker-independent queue ports."""

from collections.abc import Sequence
from typing import Protocol

from hoisa.domain.work_items import WorkflowStage, WorkItemRef


class WorkQueue(Protocol):
    """Port for reading runnable work without binding to a tracker adapter."""

    def list_runnable(self, *, stage: WorkflowStage) -> Sequence[WorkItemRef]:
        """Return runnable work item references for the requested stage."""
        ...
