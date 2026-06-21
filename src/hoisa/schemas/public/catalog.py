"""Public JSON Schema catalog for Hoisa boundary records."""

from collections.abc import Mapping

from pydantic import BaseModel

from hoisa.domain.directives import Directive
from hoisa.domain.events import WorkflowEvent
from hoisa.domain.evidence import EvidenceBundle
from hoisa.domain.gates import ApprovalGate
from hoisa.domain.runs import AgentRun
from hoisa.domain.task_packets import TaskPacket
from hoisa.domain.work_items import WorkItem

PUBLIC_SCHEMAS: Mapping[str, type[BaseModel]] = {
    "directive.schema.json": Directive,
    "work_item.schema.json": WorkItem,
    "approval_gate.schema.json": ApprovalGate,
    "agent_run.schema.json": AgentRun,
    "evidence_bundle.schema.json": EvidenceBundle,
    "task_packet.schema.json": TaskPacket,
    "workflow_event.schema.json": WorkflowEvent,
}
