"""Pydantic-free workflow event vocabulary."""

from enum import StrEnum


class WorkflowEventType(StrEnum):
    """Core event families recorded by the Hoisa workflow."""

    DIRECTIVE_CAPTURED = "directive.captured"
    SOURCE_SYNCED = "source.synced"
    SOURCE_CONFLICT_DETECTED = "source.conflict_detected"
    ISSUE_QUALITY_CHECKED = "issue.quality_checked"
    WORK_ITEM_SELECTED = "work_item.selected"
    LEASE_CLAIMED = "lease.claimed"
    TASK_PACKET_CREATED = "task_packet.created"
    PLAN_CREATED = "plan.created"
    PLAN_REVIEW_REQUESTED = "plan.review_requested"
    GATE_CREATED = "gate.created"
    GATE_DECIDED = "gate.decided"
    AGENT_RUN_STARTED = "agent_run.started"
    AGENT_RUN_COMPLETED = "agent_run.completed"
    CHECKS_COMPLETED = "checks.completed"
    PR_OPENED = "pr.opened"
    REVIEW_READY = "review.ready"
    REVIEW_CHANGES_REQUESTED = "review.changes_requested"
    INCIDENT_RECORDED = "incident.recorded"
    RETROSPECTIVE_CREATED = "retrospective.created"
