"""Human directive records that seed Hoisa work."""

from pydantic import Field

from hoisa.domain.models import CollectionRoot, HoisaModel
from hoisa.domain.privacy import PublicSafetyClass, RedactionStatus
from hoisa.domain.provenance import SourceProvenance
from hoisa.domain.target_repos import ProjectRef, TargetRepoRef
from hoisa.domain.workflow_state import ReviewRoute, RiskLevel


class DirectiveConstraints(HoisaModel):
    """Boundaries attached to a human directive."""

    in_scope: tuple[str, ...] = ()
    out_of_scope: tuple[str, ...] = ()
    required_checks: tuple[str, ...] = ()


class Directive(CollectionRoot):
    """Captured human direction before it becomes work items."""

    directive_id: str = Field(min_length=1)
    project: ProjectRef
    target_repo: TargetRepoRef | None = None
    summary: str = Field(min_length=1)
    body: str = Field(min_length=1)
    constraints: DirectiveConstraints = Field(default_factory=DirectiveConstraints)
    requested_review_route: ReviewRoute
    risk: RiskLevel
    source_provenance: SourceProvenance
    public_safety: PublicSafetyClass
    redaction_status: RedactionStatus
