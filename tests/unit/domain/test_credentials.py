from pydantic import TypeAdapter, ValidationError
import pytest

from hoisa.domain.credentials import CredentialRef


def test_credential_ref_accepts_opaque_local_slug() -> None:
    value = TypeAdapter(CredentialRef).validate_python("local:github-hoisa-workflow")

    assert value == "local:github-hoisa-workflow"


@pytest.mark.parametrize(
    "value",
    (
        "/Users/example/token",
        "local:../token",
        "local:github/token",
        "local:github;cat",
        "ghp_abcdefghijklmnopqrstuvwxyz1234567890",
        "github_pat_11_EXAMPLE",
        " github:token",
    ),
)
def test_credential_ref_rejects_paths_shell_syntax_and_token_like_values(value: str) -> None:
    with pytest.raises(ValidationError):
        TypeAdapter(CredentialRef).validate_python(value)
