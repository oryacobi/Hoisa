"""MongoDB collection and index catalog."""

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel

from hoisa.domain.events import WorkflowEvent
from hoisa.domain.evidence import EvidenceBundle
from hoisa.domain.gates import ApprovalGate
from hoisa.domain.runs import AgentRun
from hoisa.domain.sources import SourceConnection, SourceObservation, SyncCursor
from hoisa.domain.target_repos import Project, TargetRepo
from hoisa.domain.tool_control import (
    ActionRequest,
    ToolConnection,
    ToolInvocation,
    ToolPolicy,
)
from hoisa.domain.work_items import WorkItem
from hoisa.domain.workflow_state import WorkflowStateRecord

Document = dict[str, Any]
Filter = Mapping[str, Any]
SortKey = tuple[str, int]
Hint = str | tuple[SortKey, ...]
ASCENDING = 1
DESCENDING = -1


@dataclass(frozen=True, slots=True)
class MongoIndexSpec:
    """Adapter-owned MongoDB index declaration."""

    name: str
    keys: tuple[SortKey, ...]
    unique: bool = False
    partial_filter_expression: Mapping[str, Any] | None = None


@dataclass(frozen=True, slots=True)
class MongoCollectionSpec[T: BaseModel]:
    """Explicit collection mapping for a persisted Hoisa record type."""

    collection_name: str
    model_type: type[T]
    duplicate_label: str
    indexes: tuple[MongoIndexSpec, ...] = ()


MONGO_COLLECTION_SPECS: tuple[MongoCollectionSpec[Any], ...] = (
    MongoCollectionSpec(
        collection_name="projects",
        model_type=Project,
        duplicate_label="project",
    ),
    MongoCollectionSpec(
        collection_name="target_repos",
        model_type=TargetRepo,
        duplicate_label="target repository",
        indexes=(
            MongoIndexSpec(
                name="provider_owner_name_unique",
                keys=(("provider", ASCENDING), ("owner", ASCENDING), ("name", ASCENDING)),
                unique=True,
            ),
            MongoIndexSpec(
                name="project_repo_lookup",
                keys=(("project.id", ASCENDING), ("_id", ASCENDING)),
            ),
        ),
    ),
    MongoCollectionSpec(
        collection_name="source_connections",
        model_type=SourceConnection,
        duplicate_label="source connection",
        indexes=(
            MongoIndexSpec(
                name="project_target_source_status_lookup",
                keys=(
                    ("project.id", ASCENDING),
                    ("target_repo.id", ASCENDING),
                    ("source_system", ASCENDING),
                    ("status", ASCENDING),
                ),
            ),
        ),
    ),
    MongoCollectionSpec(
        collection_name="source_observations",
        model_type=SourceObservation,
        duplicate_label="source observation",
        indexes=(
            MongoIndexSpec(
                name="source_external_hash_unique",
                keys=(
                    ("source_connection_id", ASCENDING),
                    ("external_id", ASCENDING),
                    ("content_hash.value", ASCENDING),
                ),
                unique=True,
            ),
            MongoIndexSpec(
                name="source_external_hash_lookup",
                keys=(
                    ("source_connection_id", ASCENDING),
                    ("external_id", ASCENDING),
                    ("content_hash.value", ASCENDING),
                ),
            ),
        ),
    ),
    MongoCollectionSpec(
        collection_name="sync_cursors",
        model_type=SyncCursor,
        duplicate_label="sync cursor",
        indexes=(
            MongoIndexSpec(
                name="source_cursor_unique",
                keys=(("source_connection_id", ASCENDING), ("cursor_name", ASCENDING)),
                unique=True,
            ),
            MongoIndexSpec(
                name="source_cursor_lookup",
                keys=(("source_connection_id", ASCENDING), ("cursor_name", ASCENDING)),
            ),
        ),
    ),
    MongoCollectionSpec(
        collection_name="work_items",
        model_type=WorkItem,
        duplicate_label="work item tracker issue",
        indexes=(
            MongoIndexSpec(
                name="tracker_issue_unique",
                keys=(
                    ("tracker_issue.provider", ASCENDING),
                    ("tracker_issue.issue_number", ASCENDING),
                ),
                unique=True,
                partial_filter_expression={"tracker_issue": {"$exists": True}},
            ),
            MongoIndexSpec(
                name="project_target_lookup",
                keys=(("target_repo.project.id", ASCENDING), ("target_repo.id", ASCENDING)),
            ),
            MongoIndexSpec(
                name="workflow_stage_status_risk_created_lookup",
                keys=(
                    ("workflow_stage", ASCENDING),
                    ("status", ASCENDING),
                    ("risk", ASCENDING),
                    ("created_at", ASCENDING),
                    ("_id", ASCENDING),
                ),
            ),
        ),
    ),
    MongoCollectionSpec(
        collection_name="workflow_states",
        model_type=WorkflowStateRecord,
        duplicate_label="workflow state",
        indexes=(
            MongoIndexSpec(
                name="stage_status_risk_lookup",
                keys=(
                    ("state.stage", ASCENDING),
                    ("state.status", ASCENDING),
                    ("state.risk", ASCENDING),
                ),
            ),
            MongoIndexSpec(
                name="lease_worker_expiration_lookup",
                keys=(("state.lease.worker_id", ASCENDING), ("state.lease.expires_at", ASCENDING)),
            ),
            MongoIndexSpec(
                name="updated_work_item_lookup",
                keys=(("updated_at", ASCENDING), ("work_item_id", ASCENDING)),
            ),
        ),
    ),
    MongoCollectionSpec(
        collection_name="approval_gates",
        model_type=ApprovalGate,
        duplicate_label="approval gate",
        indexes=(
            MongoIndexSpec(
                name="work_item_status_stage_lookup",
                keys=(
                    ("work_item_id", ASCENDING),
                    ("gate_status", ASCENDING),
                    ("workflow_stage", ASCENDING),
                ),
            ),
            MongoIndexSpec(
                name="status_created_lookup",
                keys=(("gate_status", ASCENDING), ("created_at", ASCENDING), ("_id", ASCENDING)),
            ),
        ),
    ),
    MongoCollectionSpec(
        collection_name="agent_runs",
        model_type=AgentRun,
        duplicate_label="agent run",
        indexes=(
            MongoIndexSpec(
                name="work_item_stage_started_lookup",
                keys=(
                    ("work_item_id", ASCENDING),
                    ("workflow_stage", ASCENDING),
                    ("started_at", ASCENDING),
                    ("_id", ASCENDING),
                ),
            ),
        ),
    ),
    MongoCollectionSpec(
        collection_name="evidence_bundles",
        model_type=EvidenceBundle,
        duplicate_label="evidence bundle",
        indexes=(
            MongoIndexSpec(
                name="subject_lookup",
                keys=(("subject_type", ASCENDING), ("subject_id", ASCENDING), ("_id", ASCENDING)),
            ),
        ),
    ),
    MongoCollectionSpec(
        collection_name="tool_connections",
        model_type=ToolConnection,
        duplicate_label="tool connection",
        indexes=(
            MongoIndexSpec(
                name="project_tool_status_lookup",
                keys=(("project.id", ASCENDING), ("tool_type", ASCENDING), ("status", ASCENDING)),
            ),
        ),
    ),
    MongoCollectionSpec(
        collection_name="tool_policies",
        model_type=ToolPolicy,
        duplicate_label="tool policy",
        indexes=(
            MongoIndexSpec(
                name="project_tool_action_unique",
                keys=(
                    ("project.id", ASCENDING),
                    ("tool_type", ASCENDING),
                    ("action_type", ASCENDING),
                ),
                unique=True,
            ),
            MongoIndexSpec(
                name="project_tool_action_lookup",
                keys=(
                    ("project.id", ASCENDING),
                    ("tool_type", ASCENDING),
                    ("action_type", ASCENDING),
                ),
            ),
        ),
    ),
    MongoCollectionSpec(
        collection_name="action_requests",
        model_type=ActionRequest,
        duplicate_label="action request",
        indexes=(
            MongoIndexSpec(
                name="status_gate_created_lookup",
                keys=(
                    ("status", ASCENDING),
                    ("required_gate_id", ASCENDING),
                    ("created_at", ASCENDING),
                ),
            ),
            MongoIndexSpec(
                name="project_tool_action_lookup",
                keys=(
                    ("project.id", ASCENDING),
                    ("tool_type", ASCENDING),
                    ("action_type", ASCENDING),
                ),
            ),
        ),
    ),
    MongoCollectionSpec(
        collection_name="tool_invocations",
        model_type=ToolInvocation,
        duplicate_label="tool invocation",
        indexes=(
            MongoIndexSpec(
                name="action_request_happened_lookup",
                keys=(("action_request_id", ASCENDING), ("happened_at", ASCENDING)),
            ),
            MongoIndexSpec(
                name="tool_action_status_happened_lookup",
                keys=(
                    ("tool_type", ASCENDING),
                    ("action_type", ASCENDING),
                    ("status", ASCENDING),
                    ("happened_at", ASCENDING),
                ),
            ),
        ),
    ),
    MongoCollectionSpec(
        collection_name="workflow_events",
        model_type=WorkflowEvent,
        duplicate_label="Workflow event",
        indexes=(
            MongoIndexSpec(
                name="subject_happened_lookup",
                keys=(
                    ("subject.subject_type", ASCENDING),
                    ("subject.subject_id", ASCENDING),
                    ("happened_at", ASCENDING),
                    ("_id", ASCENDING),
                ),
            ),
            MongoIndexSpec(
                name="correlation_happened_lookup",
                keys=(
                    ("correlation_id", ASCENDING),
                    ("happened_at", ASCENDING),
                    ("_id", ASCENDING),
                ),
            ),
            MongoIndexSpec(
                name="happened_lookup",
                keys=(("happened_at", ASCENDING), ("_id", ASCENDING)),
            ),
        ),
    ),
)
