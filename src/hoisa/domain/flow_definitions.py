"""Predefined workflow flow definitions."""

from enum import StrEnum
from typing import Self

from pydantic import Field, model_validator

from hoisa.domain.models import HoisaModel

FLOW_ID_PATTERN = r"^[a-z][a-z0-9_]*$"


class FlowOwnerRole(StrEnum):
    """Role responsible for completing a flow step."""

    AGENT = "agent"
    HUMAN = "human"
    HOISA = "hoisa"


class FlowTransition(HoisaModel):
    """Allowed transition from one step to another."""

    signal: str = Field(min_length=1, pattern=FLOW_ID_PATTERN)
    to_step_id: str = Field(min_length=1, pattern=FLOW_ID_PATTERN)
    description: str = Field(min_length=1)


class FlowStep(HoisaModel):
    """One predefined step in a Hoisa flow."""

    step_id: str = Field(min_length=1, pattern=FLOW_ID_PATTERN)
    title: str = Field(min_length=1)
    owner: FlowOwnerRole
    purpose: str = Field(min_length=1)
    runner_role: str | None = Field(default=None, min_length=1)
    gate_type: str | None = Field(default=None, min_length=1, pattern=FLOW_ID_PATTERN)
    allowed_actions: tuple[str, ...] = ()
    required_evidence: tuple[str, ...] = ()
    transitions: tuple[FlowTransition, ...] = ()


class FlowDefinition(HoisaModel):
    """Repo-defined flow preset that agents may select and Hoisa can enforce."""

    flow_id: str = Field(min_length=1, pattern=FLOW_ID_PATTERN)
    title: str = Field(min_length=1)
    version: str = Field(min_length=1)
    summary: str = Field(min_length=1)
    default: bool = False
    selection_signals: tuple[str, ...] = Field(min_length=1)
    start_step_id: str = Field(min_length=1, pattern=FLOW_ID_PATTERN)
    steps: tuple[FlowStep, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_graph(self) -> Self:
        """Require a closed, deterministic step graph."""

        step_ids = [step.step_id for step in self.steps]
        unique_step_ids = set(step_ids)
        if len(unique_step_ids) != len(step_ids):
            raise ValueError("Flow step IDs must be unique.")
        if self.start_step_id not in unique_step_ids:
            raise ValueError("Flow start_step_id must reference an existing step.")

        unknown_targets = sorted(
            {
                transition.to_step_id
                for step in self.steps
                for transition in step.transitions
                if transition.to_step_id not in unique_step_ids
            }
        )
        if unknown_targets:
            raise ValueError(f"Flow transitions reference unknown steps: {unknown_targets}.")

        if not any(not step.transitions for step in self.steps):
            raise ValueError("Flow must include at least one terminal step.")

        return self
