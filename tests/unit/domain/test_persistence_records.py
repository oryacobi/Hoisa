from datetime import UTC, datetime, timedelta

from pydantic import ValidationError
import pytest

from hoisa.domain.privacy import PublicSafetyClass, RedactionStatus
from hoisa.domain.provenance import ContentHash, SourceProvenance, SourceSystem
from hoisa.domain.sources import (
    SourceConnection,
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
        id="project-sample",
        name="Sample Project",
        summary="Public-safe sample project.",
        created_at=_time(),
        updated_at=_time(1),
        source_provenance=_provenance(),
        public_safety=PublicSafetyClass.PUBLIC_SAFE_SAMPLE,
        redaction_status=RedactionStatus.NOT_REQUIRED,
    )
    target_repo = TargetRepo(
        id="repo-sample",
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

    assert project.schema_version == 1
    assert target_repo.schema_version == 1
    assert target_repo.default_branch == "main"


def test_source_records_store_summaries_cursors_and_hash_identity() -> None:
    connection = SourceConnection(
        id="source-github",
        project=_project_ref(),
        source_system=SourceSystem.GITHUB,
        display_name="Example GitHub",
        status=SourceConnectionStatus.ACTIVE,
        target_repo=_target_repo_ref(),
        created_at=_time(),
        updated_at=_time(),
        source_provenance=_provenance(source_system=SourceSystem.GITHUB),
        public_safety=PublicSafetyClass.PUBLIC_SAFE_SAMPLE,
        redaction_status=RedactionStatus.NOT_REQUIRED,
    )
    observation = SourceObservation(
        id="observation-1",
        source_connection_id=connection.id,
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
        id="cursor-1",
        source_connection_id=connection.id,
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
    assert cursor.cursor_name == "issues"


def test_source_records_reject_missing_required_identity() -> None:
    with pytest.raises(ValidationError):
        SourceObservation(
            id="",
            source_connection_id="source-github",
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
        id="work-1",
        work_item_id="work-1",
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
        id="tool-github",
        project=_project_ref(),
        tool_type="github",
        display_name="GitHub",
        status=ToolConnectionStatus.ACTIVE,
        allowed_action_summaries=("read issues",),
        created_at=_time(),
        updated_at=_time(),
        source_provenance=_provenance(),
        public_safety=PublicSafetyClass.PUBLIC_SAFE_SAMPLE,
        redaction_status=RedactionStatus.NOT_REQUIRED,
    )
    policy = ToolPolicy(
        id="policy-1",
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
        id="action-1",
        project=_project_ref(),
        tool_type="github",
        action_type="create_pull_request",
        status=ActionRequestStatus.GATED,
        summary="Request to open a PR.",
        required_gate_id="gate-1",
        created_at=_time(),
        updated_at=_time(),
        source_provenance=_provenance(),
        public_safety=PublicSafetyClass.PUBLIC_SAFE_SAMPLE,
        redaction_status=RedactionStatus.NOT_REQUIRED,
    )
    invocation = ToolInvocation(
        id="invocation-1",
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
    assert connection.allowed_action_summaries == ("read issues",)
    assert policy.decision == ToolPolicyDecision.REQUIRE_GATE
    assert request.status == ActionRequestStatus.GATED
    assert invocation.status == ToolInvocationStatus.SKIPPED


def _time(minutes: int = 0) -> datetime:
    return datetime(2026, 5, 25, 12, 0, tzinfo=UTC) + timedelta(minutes=minutes)


def _project_ref() -> ProjectRef:
    return ProjectRef(project_id="project-sample", name="Sample Project")


def _target_repo_ref() -> TargetRepoRef:
    return TargetRepoRef(
        target_repo_id="repo-sample",
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
