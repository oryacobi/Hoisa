"""Pydantic-free workflow vocabulary shared by helpers and domain models."""

from enum import StrEnum


class WorkflowStage(StrEnum):
    """Workflow stages tracked by Hoisa."""

    PLANNING = "Planning"
    PLAN_REVIEW = "Plan Review"
    PLAN_APPROVAL = "Plan Approval"
    IMPLEMENTATION = "Implementation"
    IMPLEMENTATION_REVIEW = "Implementation Review"
    IMPLEMENTED = "Implemented"


class QueueStatus(StrEnum):
    """Queue ownership status for a work item."""

    TODO = "Todo"
    IN_PROGRESS = "In Progress"
    DONE = "Done"
    BLOCKED = "Blocked"


class ReviewRoute(StrEnum):
    """Independent review route for plans and implementations."""

    HUMAN_ONLY = "Human Only"
    REVIEW_PLAN = "Review Plan"
    REVIEW_IMPLEMENTATION = "Review Implementation"
    REVIEW_BOTH = "Review Both"


class RiskLevel(StrEnum):
    """Workflow risk classification."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class WorkItemType(StrEnum):
    """High-level tracker issue type."""

    TASK = "task"
    SPIKE = "spike"
