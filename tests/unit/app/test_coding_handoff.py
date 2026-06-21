from datetime import UTC, datetime

from bson import ObjectId

from hoisa.app.services.coding_handoff import render_coding_runner_input
from hoisa.domain.evidence import EvidenceKind, EvidenceRef, EvidenceRequirement
from hoisa.domain.privacy import PublicSafetyClass, RedactionStatus
from hoisa.domain.provenance import SourceProvenance, SourceSystem
from hoisa.domain.runs import RunBudget, RunnerProfile
from hoisa.domain.target_repos import (
    ProjectRef,
    RepositoryProvider,
    RepositoryVisibility,
    TargetRepoRef,
)
from hoisa.domain.task_packets import AllowedAction, TaskPacket
from hoisa.domain.workflow_state import WorkflowStage


def test_coding_runner_input_includes_bounded_task_packet_fields() -> None:
    packet = _task_packet()

    result = render_coding_runner_input(packet)

    assert result.task_packet_id == PACKET_ID
    assert result.work_item_id == WORK_ID
    assert "Hoisa coding task packet" in result.prompt
    assert f"- task_packet_id: {PACKET_ID}" in result.prompt
    assert f"- work_item_id: {WORK_ID}" in result.prompt
    assert "- workflow_stage: Implementation" in result.prompt
    assert "Add a deterministic handoff renderer for one coding task." in result.prompt
    assert "- provider: github" in result.prompt
    assert "- repository: example-org/example-repo" in result.prompt
    assert "- visibility: public" in result.prompt
    assert "- project: Sample Project" in result.prompt
    assert "- runner_type: docker" in result.prompt
    assert "- profile_name: hoisa-codex-poc:local" in result.prompt
    assert "- sandbox: docker" in result.prompt
    assert "- network_access: no" in result.prompt
    assert "- max_minutes: 15" in result.prompt
    assert "- max_attempts: 1" in result.prompt
    assert "1. plan: docs/agent-plans/sample.md" in result.prompt
    assert "   - evidence_id: plan-sample" in result.prompt
    assert "   - summary: Public-safe approved plan summary." in result.prompt
    assert "1. edit_files" in result.prompt
    assert "   - scope: src/hoisa/app/services and tests/unit/app" in result.prompt
    assert "   - requires_gate: no" in result.prompt
    assert "- Modify only the handoff service and focused tests." in result.prompt
    assert "1. check_run: focused-tests" in result.prompt
    assert "   - required: yes" in result.prompt
    assert "   - description: Focused tests for the handoff renderer." in result.prompt


def test_coding_runner_input_excludes_workflow_control_and_private_context() -> None:
    prompt = render_coding_runner_input(_task_packet()).prompt

    excluded_terms = (
        "GitHub Project state",
        "ProjectV2",
        "approval",
        "agent_workflow.py",
        "scripts/github",
        "repo-wide planning history",
        "raw stdout",
        "raw stderr",
        "token",
        "secret",
        "/Users/",
    )

    for term in excluded_terms:
        assert term not in prompt


def test_coding_runner_input_is_deterministic() -> None:
    packet = _task_packet()

    first = render_coding_runner_input(packet)
    second = render_coding_runner_input(packet)

    assert first == second


def _task_packet() -> TaskPacket:
    return TaskPacket(
        id=PACKET_ID,
        work_item_id=WORK_ID,
        workflow_stage=WorkflowStage.IMPLEMENTATION,
        target_repo=TargetRepoRef(
            target_repo_id=REPO_ID,
            provider=RepositoryProvider.GITHUB,
            owner="example-org",
            name="example-repo",
            visibility=RepositoryVisibility.PUBLIC,
            project=ProjectRef(project_id=PROJECT_ID, name="Sample Project"),
        ),
        objective="Add a deterministic handoff renderer for one coding task.",
        context_refs=(
            EvidenceRef(
                evidence_id="plan-sample",
                kind=EvidenceKind.PLAN,
                uri="docs/agent-plans/sample.md",
                summary="Public-safe approved plan summary.",
                public_safety=PublicSafetyClass.PUBLIC_SAFE_SAMPLE,
                redaction_status=RedactionStatus.NOT_REQUIRED,
            ),
        ),
        allowed_actions=(
            AllowedAction(
                action_type="edit_files",
                scope="src/hoisa/app/services and tests/unit/app",
                requires_gate=False,
            ),
        ),
        authority_granted=("Modify only the handoff service and focused tests.",),
        runner_profile=RunnerProfile(
            runner_type="docker",
            profile_name="hoisa-codex-poc:local",
            sandbox="docker",
            network_access=False,
        ),
        budget=RunBudget(max_minutes=15, max_attempts=1),
        evidence_requirements=(
            EvidenceRequirement(
                requirement_id="focused-tests",
                kind=EvidenceKind.CHECK_RUN,
                description="Focused tests for the handoff renderer.",
                required=True,
            ),
        ),
        source_provenance=SourceProvenance(
            source_system=SourceSystem.HOISA,
            source_id="task-packet-sample",
            observed_at=datetime(2026, 6, 21, 12, 0, tzinfo=UTC),
            public_safety=PublicSafetyClass.PUBLIC_SAFE_SAMPLE,
        ),
        public_safety=PublicSafetyClass.PUBLIC_SAFE_SAMPLE,
        redaction_status=RedactionStatus.NOT_REQUIRED,
    )


PROJECT_ID = ObjectId("650000000000000000000001")
REPO_ID = ObjectId("650000000000000000000002")
WORK_ID = ObjectId("650000000000000000000003")
PACKET_ID = ObjectId("650000000000000000000004")
