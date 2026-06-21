import asyncio
from collections.abc import Coroutine
from datetime import UTC, datetime, timedelta
import inspect
import os
from typing import Any
from uuid import uuid4

from antonic import AntConnector
import pytest

from hoisa.adapters.persistence.antonic import AntonicPersistenceProvider
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
from hoisa.ports.persistence import RepoLookup, RunnableWorkQuery, WaitingGateQuery


def test_antonic_provider_uses_configured_local_mongo_instance() -> None:
    uri = os.environ.get("HOISA_MONGO_TEST_URI") or os.environ.get("MONGODB_URI")
    if uri is None:
        pytest.skip("Set HOISA_MONGO_TEST_URI or MONGODB_URI to run the Antonic Mongo contract.")

    database = os.environ.get("HOISA_MONGO_TEST_DATABASE") or f"hoisa_test_{uuid4().hex}"
    run(_exercise_provider(uri, database))


async def _exercise_provider(uri: str, database: str) -> None:
    connector = AntConnector(uri, database=database)
    provider = AntonicPersistenceProvider(connector)

    try:
        await provider.ensure_indexes()
        await provider.projects.save(_project())
        await provider.target_repos.save(_target_repo())
        await provider.work_items.save(_work_item("work-1", issue_number=9))
        await provider.workflow_states.save(_state("work-1"))
        await provider.gates.save(_gate("gate-1", work_item_id="work-1"))

        assert await provider.projects.get("project-sample") is not None
        assert await provider.target_repos.get_by_provider(_repo_lookup()) is not None
        assert await provider.work_items.find_by_tracker_issue(provider="github", issue_number=9)
        assert [
            item.id
            for item in await provider.work_items.find_runnable(
                RunnableWorkQuery(workflow_stage=WorkflowStage.IMPLEMENTATION, now=_time(1))
            )
        ] == ["work-1"]
        assert [
            gate.id
            for gate in await provider.gates.list_waiting(WaitingGateQuery(tracker_issue_number=9))
        ] == ["gate-1"]
    finally:
        result = connector.client.drop_database(database)
        if inspect.isawaitable(result):
            await result
        await provider.close()


def run[T](coro: Coroutine[Any, Any, T]) -> T:
    return asyncio.run(coro)


def _project() -> Project:
    return Project(
        id="project-sample",
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
        id="repo-sample",
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


def _work_item(work_item_id: str, *, issue_number: int) -> WorkItem:
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


def _state(work_item_id: str) -> WorkflowStateRecord:
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


def _gate(gate_id: str, *, work_item_id: str) -> ApprovalGate:
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
