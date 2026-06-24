"""Opaque credential references for private runtime secret resolution."""

import re
from typing import Annotated

from pydantic import AfterValidator, Field, WithJsonSchema

_CREDENTIAL_REF_RE = re.compile(r"^[a-z][a-z0-9_.-]*:[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$")
_TOKEN_PREFIXES = ("ghp_", "gho_", "ghu_", "ghs_", "ghr_", "github_pat_")


def validate_credential_ref(value: str) -> str:
    """Validate an opaque, non-secret credential reference."""

    if not isinstance(value, str):
        raise ValueError("Credential reference must be a string.")
    candidate = value.strip()
    if candidate != value or not candidate:
        raise ValueError("Credential reference must not be blank or padded.")
    lowered = candidate.lower()
    if lowered.startswith(_TOKEN_PREFIXES):
        raise ValueError("Credential reference must not look like a GitHub token.")
    if not _CREDENTIAL_REF_RE.fullmatch(candidate):
        raise ValueError(
            "Credential reference must be an opaque slug like 'local:github-hoisa-workflow'."
        )
    if any(marker in candidate for marker in ("/", "\\", "..", "$", "`", "|", "&", ";")):
        raise ValueError("Credential reference must not contain path or shell syntax.")
    return candidate


CredentialRef = Annotated[
    str,
    Field(min_length=3, max_length=160),
    AfterValidator(validate_credential_ref),
    WithJsonSchema(
        {
            "type": "string",
            "pattern": r"^[a-z][a-z0-9_.-]*:[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$",
            "examples": ["local:github-hoisa-workflow"],
        }
    ),
]
