import asyncio
from collections.abc import Coroutine
from datetime import UTC, datetime, timedelta
import inspect
import os
from typing import Any
from uuid import uuid4

from bson import ObjectId
import pytest

from hoisa.adapters.persistence.antonic import HoisaAntConnector
from hoisa.domain.evidence import EvidenceKind, EvidenceRef
from hoisa.domain.gates import (
    ApprovalGate,
    GateOption,
    GateRecommendation,
    GateStatus,
    GateType,
)
from hoisa.domain.privacy import PublicSafetyClass, RedactionStatus
from hoisa.domain.provenance import SourceProvenance, SourceSystem
from hoisa.domain.target_repos import (
    Project,
    ProjectRef,
    RepositoryProvider,
    RepositoryVisibility,
    TargetRepo,
    TargetRepoRef,
)
from hoisa.domain.work_items import TrackerIssueRef, WorkItem
from hoisa.domain.workflow_state import (
    QueueStatus,
    ReviewRoute,
    RiskLevel,
    WorkflowStage,
    WorkflowState,
    WorkflowStateRecord,
    WorkItemType,
)
from hoisa.ports.persistence import (
    RepoLookup,
    RunnableWorkQuery,
    WaitingGateQuery,
    repo_lookup_filter,
)


def test_hoisa_ant_connector_uses_configured_local_mongo_instance() -> None:
    uri = os.environ.get("HOISA_MONGO_TEST_URI") or os.environ.get("MONGODB_URI")
    if uri is None:
        pytest.skip("Set HOISA_MONGO_TEST_URI or MONGODB_URI to run the Antonic Mongo contract.")

    database = os.environ.get("HOISA_MONGO_TEST_DATABASE") or f"hoisa_test_{uuid4().hex}"
    run(_exercise_connector(uri, database))


async def _exercise_connector(uri: str, database: str) -> None:
    connector = HoisaAntConnector(uri, database=database)

    try:
        await connector.ensure_indexes()
        await connector.insert(_project())
        await connector.insert(_target_repo())
        await connector.insert(_work_item(WORK_ID, issue_number=9))
        await connector.insert(_state(WORK_ID))
        await connector.insert(_gate(GATE_ID, work_item_id=WORK_ID))

        assert await connector.get(Project, PROJECT_ID) is not None
        assert (
            await connector.get(TargetRepo, filter=repo_lookup_filter(_repo_lookup())) is not None
        )
        assert await connector.get(WorkItem, filter={"tracker_issue.issue_number": 9})
        assert [
            item.id
            for item in await connector.find_runnable_work(
                RunnableWorkQuery(workflow_stage=WorkflowStage.IMPLEMENTATION, now=_time(1))
            )
        ] == [WORK_ID]
        assert [
            gate.id
            for gate in await connector.list_waiting_gates(WaitingGateQuery(tracker_issue_number=9))
        ] == [GATE_ID]
    finally:
        result = connector.client.drop_database(database)
        if inspect.isawaitable(result):
            await result
        await connector.close()


def run[T](coro: Coroutine[Any, Any, T]) -> T:
    return asyncio.run(coro)


def _project() -> Project:
    return Project(
        id=PROJECT_ID,
        name="Sample Project",
        summary="Public-safe sample project.",
        created_at=_time(),
        updated_at=_time(),
        source_provenance=_provenance(),
        public_safety=PublicSafetyClass.PUBLIC_SAFE_SAMPLE,
        redaction_status=RedactionStatus.NOT_REQUIRED,
    )


def _target_repo() -> TargetRepo:
    return TargetRepo(
        id=REPO_ID,
        provider=RepositoryProvider.GITHUB,
        owner="example-org",
        name="example-repo",
        visibility=RepositoryVisibility.PUBLIC,
        project=_project_ref(),
        default_branch="main",
        created_at=_time(),
        updated_at=_time(),
        source_provenance=_provenance(),
        public_safety=PublicSafetyClass.PUBLIC_SAFE_SAMPLE,
        redaction_status=RedactionStatus.NOT_REQUIRED,
    )


def _work_item(work_item_id: ObjectId, *, issue_number: int) -> WorkItem:
    return WorkItem(
        id=work_item_id,
        item_type=WorkItemType.TASK,
        title=f"Issue {issue_number}",
        goal="Implement a public-safe sample task.",
        target_repo=_target_repo_ref(),
        tracker_issue=TrackerIssueRef(
            tracker_issue_id=f"issue-{issue_number}",
            provider="github",
            issue_number=issue_number,
            title=f"Issue {issue_number}",
            url=f"https://github.com/example-org/example-repo/issues/{issue_number}",
        ),
        workflow_stage=WorkflowStage.IMPLEMENTATION,
        status=QueueStatus.TODO,
        review_route=ReviewRoute.REVIEW_BOTH,
        risk=RiskLevel.HIGH,
        quality_status="ready",
        created_at=_time(issue_number),
        updated_at=_time(issue_number),
        source_provenance=_provenance(),
        public_safety=PublicSafetyClass.PUBLIC_SAFE_SAMPLE,
        redaction_status=RedactionStatus.NOT_REQUIRED,
    )


def _state(work_item_id: ObjectId) -> WorkflowStateRecord:
    return WorkflowStateRecord(
        id=work_item_id,
        work_item_id=work_item_id,
        state=WorkflowState(
            stage=WorkflowStage.IMPLEMENTATION,
            status=QueueStatus.TODO,
            review_route=ReviewRoute.REVIEW_BOTH,
            risk=RiskLevel.HIGH,
        ),
        created_at=_time(),
        updated_at=_time(),
        source_provenance=_provenance(),
        public_safety=PublicSafetyClass.PUBLIC_SAFE_SAMPLE,
        redaction_status=RedactionStatus.NOT_REQUIRED,
    )


def _gate(gate_id: ObjectId, *, work_item_id: ObjectId) -> ApprovalGate:
    return ApprovalGate(
        id=gate_id,
        gate_type=GateType.PLAN_APPROVAL,
        gate_status=GateStatus.WAITING,
        work_item_id=work_item_id,
        workflow_stage=WorkflowStage.PLAN_APPROVAL,
        risk=RiskLevel.HIGH,
        recommendation=GateRecommendation.APPROVE,
        decision_needed="Approve implementation.",
        why_human_needed="A human approval gate is required.",
        authority_granted="Implement only the approved plan.",
        options=(GateOption.APPROVE, GateOption.REQUEST_CHANGES),
        evidence_refs=(_evidence_ref(),),
        created_at=_time(),
        updated_at=_time(),
        source_provenance=_provenance(),
        public_safety=PublicSafetyClass.PUBLIC_SAFE_SAMPLE,
        redaction_status=RedactionStatus.NOT_REQUIRED,
    )


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


def _repo_lookup() -> RepoLookup:
    return RepoLookup(
        provider=RepositoryProvider.GITHUB,
        owner="example-org",
        name="example-repo",
    )


def _evidence_ref() -> EvidenceRef:
    return EvidenceRef(
        evidence_id="evidence-plan",
        kind=EvidenceKind.PLAN,
        uri="docs/agent-plans/sample.md",
        summary="Public-safe plan.",
        public_safety=PublicSafetyClass.PUBLIC_SAFE_SAMPLE,
        redaction_status=RedactionStatus.NOT_REQUIRED,
    )


def _provenance(source_system: SourceSystem = SourceSystem.HOISA) -> SourceProvenance:
    return SourceProvenance(
        source_system=source_system,
        source_id="source-sample",
        observed_at=_time(),
        source_url="https://github.com/example-org/example-repo/issues/9",
        public_safety=PublicSafetyClass.PUBLIC_SAFE_SAMPLE,
    )


PROJECT_ID = ObjectId("650000000000000000000001")
REPO_ID = ObjectId("650000000000000000000002")
WORK_ID = ObjectId("650000000000000000000003")
GATE_ID = ObjectId("650000000000000000000004")
