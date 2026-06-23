from datetime import UTC, datetime, timedelta
from typing import Any, cast

from bson import ObjectId
from pydantic import ValidationError
import pytest

from hoisa.domain.privacy import PublicSafetyClass, RedactionStatus
from hoisa.domain.provenance import ContentHash, SourceProvenance, SourceSystem
from hoisa.domain.sources import (
    SourceConnection,
    SourceConnectionResourceType,
    SourceConnectionStatus,
    SourceObservation,
    SyncCursor,
)
from hoisa.domain.target_repos import (
    Project,
    ProjectRef,
    RepositoryProvider,
    RepositoryVisibility,
    TargetRepo,
    TargetRepoRef,
)
from hoisa.domain.tool_control import (
    ActionRequest,
    ActionRequestStatus,
    ToolConnection,
    ToolConnectionStatus,
    ToolInvocation,
    ToolInvocationStatus,
    ToolPolicy,
    ToolPolicyDecision,
)
from hoisa.domain.workflow_state import (
    Lease,
    QueueStatus,
    ReviewRoute,
    RiskLevel,
    WorkflowStage,
    WorkflowState,
    WorkflowStateRecord,
)


def test_persistence_collection_roots_carry_versioned_public_safe_metadata() -> None:
    project = Project(
        id=PROJECT_ID,
        name="Sample Project",
        summary="Public-safe sample project.",
        created_at=_time(),
        updated_at=_time(1),
        source_provenance=_provenance(),
        public_safety=PublicSafetyClass.PUBLIC_SAFE_SAMPLE,
        redaction_status=RedactionStatus.NOT_REQUIRED,
    )
    target_repo = TargetRepo(
        id=REPO_ID,
        provider=RepositoryProvider.GITHUB,
        owner="example-org",
        name="example-repo",
        visibility=RepositoryVisibility.PUBLIC,
        project=_project_ref(),
        default_branch="main",
        created_at=_time(),
        updated_at=_time(1),
        source_provenance=_provenance(),
        public_safety=PublicSafetyClass.PUBLIC_SAFE_SAMPLE,
        redaction_status=RedactionStatus.NOT_REQUIRED,
    )

    assert project.id == PROJECT_ID
    assert target_repo.project.project_id == PROJECT_ID
    assert target_repo.default_branch == "main"


def test_source_records_store_summaries_cursors_and_hash_identity() -> None:
    connection = SourceConnection(
        id=SOURCE_ID,
        project=_project_ref(),
        source_system=SourceSystem.GITHUB,
        display_name="Example GitHub",
        status=SourceConnectionStatus.ACTIVE,
        target_repo=_target_repo_ref(),
        resource_type=SourceConnectionResourceType.GITHUB_REPOSITORY_ISSUES,
        external_node_id=None,
        display_url="https://github.com/example-org/example-repo",
        credential_ref="local:github-example-workflow",
        created_at=_time(),
        updated_at=_time(),
        source_provenance=_provenance(source_system=SourceSystem.GITHUB),
        public_safety=PublicSafetyClass.PUBLIC_SAFE_SAMPLE,
        redaction_status=RedactionStatus.NOT_REQUIRED,
    )
    connection_id = connection.id
    assert isinstance(connection_id, ObjectId)
    observation = SourceObservation(
        id=OBSERVATION_ID,
        source_connection_id=connection_id,
        external_id="issue-9",
        content_hash=_hash(),
        summary="Issue metadata summary.",
        payload_schema="github_issue_summary.v1",
        payload={"issue_number": 9, "state": "open"},
        created_at=_time(),
        updated_at=_time(),
        source_provenance=_provenance(source_system=SourceSystem.GITHUB),
        public_safety=PublicSafetyClass.PUBLIC_SAFE_SAMPLE,
        redaction_status=RedactionStatus.NOT_REQUIRED,
    )
    cursor = SyncCursor(
        id=CURSOR_ID,
        source_connection_id=connection_id,
        cursor_name="issues",
        cursor_value="2026-05-25T12:00:00Z",
        created_at=_time(),
        updated_at=_time(),
        source_provenance=_provenance(source_system=SourceSystem.GITHUB),
        public_safety=PublicSafetyClass.PUBLIC_SAFE_SAMPLE,
        redaction_status=RedactionStatus.NOT_REQUIRED,
    )

    assert observation.content_hash.value == "abc123"
    assert observation.payload["issue_number"] == 9
    assert connection.resource_type == SourceConnectionResourceType.GITHUB_REPOSITORY_ISSUES
    assert connection.credential_ref == "local:github-example-workflow"
    assert cursor.cursor_name == "issues"


def test_source_records_reject_missing_required_identity() -> None:
    with pytest.raises(ValidationError):
        SourceObservation(
            id=cast(Any, ""),
            source_connection_id=cast(Any, "source-github"),
            external_id="issue-9",
            content_hash=_hash(),
            summary="Issue metadata summary.",
            payload_schema="github_issue_summary.v1",
            created_at=_time(),
            updated_at=_time(),
            source_provenance=_provenance(),
            public_safety=PublicSafetyClass.PUBLIC_SAFE_SAMPLE,
            redaction_status=RedactionStatus.NOT_REQUIRED,
        )


def test_workflow_state_and_tool_control_records_do_not_authorize_actions() -> None:
    state = WorkflowStateRecord(
        id=WORK_ID,
        work_item_id=WORK_ID,
        state=WorkflowState(
            stage=WorkflowStage.IMPLEMENTATION,
            status=QueueStatus.IN_PROGRESS,
            review_route=ReviewRoute.REVIEW_BOTH,
            risk=RiskLevel.HIGH,
            lease=Lease(
                worker_id="Codex-2",
                claimed_at=_time(),
                expires_at=_time(30),
            ),
        ),
        created_at=_time(),
        updated_at=_time(),
        source_provenance=_provenance(),
        public_safety=PublicSafetyClass.PUBLIC_SAFE_SAMPLE,
        redaction_status=RedactionStatus.NOT_REQUIRED,
    )
    connection = ToolConnection(
        id=TOOL_CONNECTION_ID,
        project=_project_ref(),
        tool_type="github",
        display_name="GitHub",
        status=ToolConnectionStatus.ACTIVE,
        credential_ref="local:github-example-workflow",
        allowed_action_summaries=("read issues",),
        created_at=_time(),
        updated_at=_time(),
        source_provenance=_provenance(),
        public_safety=PublicSafetyClass.PUBLIC_SAFE_SAMPLE,
        redaction_status=RedactionStatus.NOT_REQUIRED,
    )
    policy = ToolPolicy(
        id=POLICY_ID,
        project=_project_ref(),
        tool_type="github",
        action_type="create_pull_request",
        decision=ToolPolicyDecision.REQUIRE_GATE,
        required_gate_type="merge_readiness",
        summary="Require a gate before PR creation.",
        created_at=_time(),
        updated_at=_time(),
        source_provenance=_provenance(),
        public_safety=PublicSafetyClass.PUBLIC_SAFE_SAMPLE,
        redaction_status=RedactionStatus.NOT_REQUIRED,
    )
    request = ActionRequest(
        id=ACTION_ID,
        project=_project_ref(),
        tool_type="github",
        action_type="create_pull_request",
        status=ActionRequestStatus.GATED,
        summary="Request to open a PR.",
        required_gate_id=GATE_ID,
        created_at=_time(),
        updated_at=_time(),
        source_provenance=_provenance(),
        public_safety=PublicSafetyClass.PUBLIC_SAFE_SAMPLE,
        redaction_status=RedactionStatus.NOT_REQUIRED,
    )
    invocation = ToolInvocation(
        id=INVOCATION_ID,
        tool_type="github",
        action_type="create_pull_request",
        status=ToolInvocationStatus.SKIPPED,
        happened_at=_time(),
        summary="Skipped until gate approval.",
        action_request_id=request.id,
        created_at=_time(),
        updated_at=_time(),
        source_provenance=_provenance(),
        public_safety=PublicSafetyClass.PUBLIC_SAFE_SAMPLE,
        redaction_status=RedactionStatus.NOT_REQUIRED,
    )

    assert state.state.lease is not None
    assert connection.credential_ref == "local:github-example-workflow"
    assert connection.allowed_action_summaries == ("read issues",)
    assert policy.decision == ToolPolicyDecision.REQUIRE_GATE
    assert request.status == ActionRequestStatus.GATED
    assert invocation.status == ToolInvocationStatus.SKIPPED


def _time(minutes: int = 0) -> datetime:
    return datetime(2026, 5, 25, 12, 0, tzinfo=UTC) + timedelta(minutes=minutes)


def _project_ref() -> ProjectRef:
    return ProjectRef(project_id=PROJECT_ID, name="Sample Project")


def _target_repo_ref() -> TargetRepoRef:
    return TargetRepoRef(
        target_repo_id=REPO_ID,
        provider=RepositoryProvider.GITHUB,
        owner="example-org",
        name="example-repo",
        visibility=RepositoryVisibility.PUBLIC,
        project=_project_ref(),
    )


def _provenance(source_system: SourceSystem = SourceSystem.HOISA) -> SourceProvenance:
    return SourceProvenance(
        source_system=source_system,
        source_id="source-sample",
        observed_at=_time(),
        source_url="https://github.com/example-org/example-repo/issues/9",
        public_safety=PublicSafetyClass.PUBLIC_SAFE_SAMPLE,
    )


def _hash() -> ContentHash:
    return ContentHash(algorithm="sha256", value="abc123")


PROJECT_ID = ObjectId("650000000000000000000001")
REPO_ID = ObjectId("650000000000000000000002")
SOURCE_ID = ObjectId("650000000000000000000003")
OBSERVATION_ID = ObjectId("650000000000000000000004")
CURSOR_ID = ObjectId("650000000000000000000005")
WORK_ID = ObjectId("650000000000000000000006")
TOOL_CONNECTION_ID = ObjectId("650000000000000000000007")
POLICY_ID = ObjectId("650000000000000000000008")
ACTION_ID = ObjectId("650000000000000000000009")
INVOCATION_ID = ObjectId("65000000000000000000000a")
GATE_ID = ObjectId("65000000000000000000000b")
