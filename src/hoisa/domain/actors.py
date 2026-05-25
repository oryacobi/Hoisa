"""Actors that participate in workflow events, gates, and runs."""

from enum import StrEnum

from pydantic import Field

from hoisa.domain.models import HoisaModel


class ActorType(StrEnum):
    """Kinds of actors Hoisa records in workflow history."""

    HUMAN = "human"
    AGENT = "agent"
    SERVICE = "service"
    SYSTEM = "system"


class ActorRef(HoisaModel):
    """Stable actor reference without leaking channel-specific identity data."""

    actor_type: ActorType
    actor_id: str = Field(min_length=1)
    display_name: str | None = None
