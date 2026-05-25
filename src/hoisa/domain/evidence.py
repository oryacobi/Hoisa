"""Evidence references and bundles for Hoisa review surfaces."""

from enum import StrEnum

from pydantic import Field

from hoisa.domain.models import CollectionRoot, HoisaModel
from hoisa.domain.privacy import PublicSafetyClass, RedactionStatus
from hoisa.domain.provenance import ContentHash, SourceProvenance


class EvidenceKind(StrEnum):
    """Kinds of evidence Hoisa can cite without embedding raw artifacts."""

    ISSUE = "issue"
    PLAN = "plan"
    PULL_REQUEST = "pull_request"
    CHECK_RUN = "check_run"
    REPO_FILE = "repo_file"
    COMMAND_SUMMARY = "command_summary"
    REDACTED_SUMMARY = "redacted_summary"
    SCHEMA_FIXTURE = "schema_fixture"


class EvidenceRef(HoisaModel):
    """Reference to evidence with summary and redaction metadata."""

    evidence_id: str = Field(min_length=1)
    kind: EvidenceKind
    uri: str = Field(min_length=1)
    summary: str = Field(min_length=1)
    content_hash: ContentHash | None = None
    source_provenance: SourceProvenance | None = None
    public_safety: PublicSafetyClass
    redaction_status: RedactionStatus


class EvidenceRequirement(HoisaModel):
    """Evidence that a task packet or gate expects a run to produce."""

    requirement_id: str = Field(min_length=1)
    kind: EvidenceKind
    description: str = Field(min_length=1)
    required: bool = True


class EvidenceBundle(CollectionRoot):
    """Collection-root evidence package for review and audit."""

    bundle_id: str = Field(min_length=1)
    subject_type: str = Field(min_length=1)
    subject_id: str = Field(min_length=1)
    refs: tuple[EvidenceRef, ...] = Field(min_length=1)
    source_provenance: SourceProvenance | None = None
    public_safety: PublicSafetyClass
    redaction_status: RedactionStatus
