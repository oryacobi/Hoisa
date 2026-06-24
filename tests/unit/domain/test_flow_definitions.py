from pathlib import Path

from pydantic import ValidationError
import pytest

from hoisa.app.workflows.flow_catalog import FlowCatalogError, load_flow_catalog
from hoisa.domain.flow_definitions import FlowDefinition, FlowOwnerRole

PROJECT_ROOT = Path(__file__).resolve().parents[3]
FLOW_ROOT = PROJECT_ROOT / "flows"


def test_initial_repo_flow_catalog_contains_only_coding_and_research() -> None:
    catalog = load_flow_catalog(FLOW_ROOT)

    assert set(catalog) == {"coding_feature", "research_report"}
    assert catalog["coding_feature"].default is True
    assert catalog["research_report"].default is False


def test_checked_in_flow_definitions_are_closed_graphs() -> None:
    for path in sorted(FLOW_ROOT.glob("*/flow.json")):
        flow = FlowDefinition.model_validate_json(path.read_text(encoding="utf-8"))
        step_ids = {step.step_id for step in flow.steps}
        terminal_steps = [step for step in flow.steps if not step.transitions]

        assert flow.flow_id == path.parent.name
        assert flow.start_step_id in step_ids
        assert terminal_steps


def test_coding_feature_flow_keeps_human_gates_explicit() -> None:
    flow = load_flow_catalog(FLOW_ROOT)["coding_feature"]
    human_steps = [step for step in flow.steps if step.owner == FlowOwnerRole.HUMAN]

    assert {step.step_id for step in human_steps} == {"plan_approval", "human_verification"}
    assert {step.gate_type for step in human_steps} == {"plan_approval", "merge_readiness"}


def test_research_report_flow_includes_research_draft_and_verification() -> None:
    flow = load_flow_catalog(FLOW_ROOT)["research_report"]
    step_ids = {step.step_id for step in flow.steps}

    assert {"source_research", "draft_report", "verify_claims"}.issubset(step_ids)


def test_flow_catalog_rejects_directory_id_mismatch(tmp_path: Path) -> None:
    flow_dir = tmp_path / "wrong"
    flow_dir.mkdir()
    (flow_dir / "flow.json").write_text(
        (FLOW_ROOT / "coding_feature" / "flow.json").read_text(encoding="utf-8"),
        encoding="utf-8",
    )

    with pytest.raises(FlowCatalogError, match="does not match directory"):
        load_flow_catalog(tmp_path)


def test_flow_definition_rejects_unknown_transition_target() -> None:
    source = FlowDefinition.model_validate_json(
        (FLOW_ROOT / "coding_feature" / "flow.json").read_text(encoding="utf-8")
    )
    payload = source.model_dump(mode="json")
    payload["steps"][0]["transitions"][0]["to_step_id"] = "missing_step"

    with pytest.raises(ValidationError, match="unknown steps"):
        FlowDefinition.model_validate(payload)
