"""Render bounded task packets for coding runners."""

from dataclasses import dataclass

from hoisa.domain.evidence import EvidenceRef, EvidenceRequirement
from hoisa.domain.models import RecordId
from hoisa.domain.runs import RunBudget, RunnerProfile
from hoisa.domain.target_repos import TargetRepoRef
from hoisa.domain.task_packets import AllowedAction, TaskPacket


@dataclass(frozen=True, slots=True)
class CodingRunnerInput:
    """Deterministic input prepared for a coding runner."""

    task_packet_id: RecordId | None
    work_item_id: RecordId
    prompt: str


def render_coding_runner_input(packet: TaskPacket) -> CodingRunnerInput:
    """Render the task-packet fields a coding runner needs."""

    return CodingRunnerInput(
        task_packet_id=packet.id,
        work_item_id=packet.work_item_id,
        prompt="\n".join(_prompt_lines(packet)),
    )


def _prompt_lines(packet: TaskPacket) -> tuple[str, ...]:
    lines: list[str] = [
        "Hoisa coding task packet",
        "",
        "Task identity",
        f"- task_packet_id: {_record_id(packet.id)}",
        f"- work_item_id: {_record_id(packet.work_item_id)}",
        f"- workflow_stage: {packet.workflow_stage.value}",
        "",
        "Objective",
        packet.objective,
        "",
        "Target repository",
        *_target_repo_lines(packet.target_repo),
        "",
        "Runner profile",
        *_runner_profile_lines(packet.runner_profile),
        "",
        "Budget",
        *_budget_lines(packet.budget),
        "",
        "Context references",
        *_evidence_ref_lines(packet.context_refs),
        "",
        "Allowed actions",
        *_allowed_action_lines(packet.allowed_actions),
        "",
        "Authority",
        *_authority_lines(packet.authority_granted),
        "",
        "Expected evidence",
        *_evidence_requirement_lines(packet.evidence_requirements),
        "",
        "Runner boundary",
        "- Use only the task packet above as execution context.",
        "- Return compact evidence summaries suitable for Hoisa review.",
    ]
    return tuple(lines)


def _target_repo_lines(target_repo: TargetRepoRef) -> tuple[str, ...]:
    return (
        f"- provider: {target_repo.provider.value}",
        f"- repository: {target_repo.owner}/{target_repo.name}",
        f"- visibility: {target_repo.visibility.value}",
        f"- project: {target_repo.project.name}",
    )


def _runner_profile_lines(profile: RunnerProfile) -> tuple[str, ...]:
    return (
        f"- runner_type: {profile.runner_type}",
        f"- profile_name: {profile.profile_name}",
        f"- sandbox: {profile.sandbox}",
        f"- network_access: {_yes_no(profile.network_access)}",
    )


def _budget_lines(budget: RunBudget) -> tuple[str, ...]:
    return (
        f"- max_minutes: {budget.max_minutes}",
        f"- max_attempts: {budget.max_attempts}",
    )


def _evidence_ref_lines(refs: tuple[EvidenceRef, ...]) -> tuple[str, ...]:
    lines: list[str] = []
    for index, ref in enumerate(refs, start=1):
        lines.extend(
            (
                f"{index}. {ref.kind.value}: {ref.uri}",
                f"   - evidence_id: {ref.evidence_id}",
                f"   - summary: {ref.summary}",
                f"   - public_safety: {ref.public_safety.value}",
                f"   - redaction_status: {ref.redaction_status.value}",
            )
        )
    return tuple(lines)


def _allowed_action_lines(actions: tuple[AllowedAction, ...]) -> tuple[str, ...]:
    if not actions:
        return ("- none",)

    lines: list[str] = []
    for index, action in enumerate(actions, start=1):
        lines.extend(
            (
                f"{index}. {action.action_type}",
                f"   - scope: {action.scope}",
                f"   - requires_gate: {_yes_no(action.requires_gate)}",
            )
        )
    return tuple(lines)


def _authority_lines(authority_granted: tuple[str, ...]) -> tuple[str, ...]:
    if not authority_granted:
        return ("- none",)
    return tuple(f"- {authority}" for authority in authority_granted)


def _evidence_requirement_lines(
    requirements: tuple[EvidenceRequirement, ...],
) -> tuple[str, ...]:
    lines: list[str] = []
    for index, requirement in enumerate(requirements, start=1):
        lines.extend(
            (
                f"{index}. {requirement.kind.value}: {requirement.requirement_id}",
                f"   - required: {_yes_no(requirement.required)}",
                f"   - description: {requirement.description}",
            )
        )
    return tuple(lines)


def _record_id(value: RecordId | None) -> str:
    if value is None:
        return "unassigned"
    return str(value)


def _yes_no(value: bool) -> str:
    return "yes" if value else "no"
