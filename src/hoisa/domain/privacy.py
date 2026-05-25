"""Public safety and redaction vocabulary for exportable Hoisa records."""

from enum import StrEnum


class PublicSafetyClass(StrEnum):
    """Classification for records crossing public or review boundaries."""

    PUBLIC = "public"
    PUBLIC_SAFE_SAMPLE = "public_safe_sample"
    REDACTED = "redacted"
    PRIVATE_REFERENCE = "private_reference"


class RedactionStatus(StrEnum):
    """Whether a record or reference has been redacted for public use."""

    NOT_REQUIRED = "not_required"
    REDACTED = "redacted"
    SUMMARY_ONLY = "summary_only"
