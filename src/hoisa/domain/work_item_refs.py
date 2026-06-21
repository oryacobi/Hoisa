"""Pydantic-free work item references."""

from dataclasses import dataclass

from bson import ObjectId


@dataclass(frozen=True, slots=True)
class WorkItemRef:
    """Tracker-independent reference to a Hoisa work item."""

    value: ObjectId
