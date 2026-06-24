"""Local private-file GitHub credential resolver."""

from pathlib import Path
import stat

from pydantic import Field, field_validator

from hoisa.app.services.github_connection_bootstrap import (
    GitHubBootstrapRequest,
)
from hoisa.domain.credentials import CredentialRef
from hoisa.domain.models import HoisaModel
from hoisa.domain.target_repos import RepositoryVisibility
from hoisa.ports.credentials import (
    CredentialResolutionError,
    CredentialResolver,
    GitHubAppCredentialMaterial,
)


class GitHubBootstrapManifest(HoisaModel):
    """Private local manifest for bootstrapping one GitHub repo connection."""

    credential_ref: CredentialRef
    app_id: int = Field(gt=0)
    installation_id: int = Field(gt=0)
    private_key_file: str = Field(min_length=1)
    repo_owner: str = Field(min_length=1)
    repo_name: str = Field(min_length=1)
    repo_visibility: RepositoryVisibility = RepositoryVisibility.PRIVATE
    hoisa_project_name: str | None = Field(default=None, min_length=1)
    api_base_url: str = "https://api.github.com"

    @field_validator("private_key_file")
    @classmethod
    def validate_private_key_file(cls, value: str) -> str:
        """Require a local filename, not an absolute or nested path."""

        path = Path(value)
        if path.is_absolute() or len(path.parts) != 1 or value in {".", ".."}:
            raise ValueError("private_key_file must be a relative filename in the manifest dir.")
        if any(marker in value for marker in ("/", "\\", "$", "`", "|", "&", ";")):
            raise ValueError("private_key_file must not contain path or shell syntax.")
        return value

    def bootstrap_request(self) -> GitHubBootstrapRequest:
        """Return the public-safe bootstrap request carried by this manifest."""

        return GitHubBootstrapRequest(
            credential_ref=self.credential_ref,
            repo_owner=self.repo_owner,
            repo_name=self.repo_name,
            repo_visibility=self.repo_visibility,
            hoisa_project_name=self.hoisa_project_name,
        )


class LocalGitHubAppCredentialResolver(CredentialResolver):
    """Resolve GitHub App material from ignored local JSON and PEM files."""

    def __init__(
        self, manifests: dict[CredentialRef, tuple[GitHubBootstrapManifest, Path]]
    ) -> None:
        self._manifests = manifests

    @classmethod
    def from_manifest_file(cls, path: Path) -> "LocalGitHubAppCredentialResolver":
        """Create a resolver scoped to one private manifest file."""

        manifest = load_github_bootstrap_manifest(path)
        return cls({manifest.credential_ref: (manifest, path.resolve())})

    def resolve_github_app(self, credential_ref: CredentialRef) -> GitHubAppCredentialMaterial:
        """Read GitHub App auth material for the requested ref."""

        entry = self._manifests.get(credential_ref)
        if entry is None:
            raise CredentialResolutionError(f"Unknown GitHub credential ref: {credential_ref}")
        manifest, manifest_path = entry
        key_path = manifest_path.parent / manifest.private_key_file
        _validate_private_key_path(key_path)
        try:
            private_key_pem = key_path.read_text(encoding="utf-8")
        except OSError as exc:
            raise CredentialResolutionError("Could not read GitHub App private key.") from exc
        if "PRIVATE KEY" not in private_key_pem:
            raise CredentialResolutionError("GitHub App private key file is not a PEM key.")
        return GitHubAppCredentialMaterial(
            credential_ref=credential_ref,
            app_id=manifest.app_id,
            installation_id=manifest.installation_id,
            private_key_pem=private_key_pem,
        )


def load_github_bootstrap_manifest(path: Path) -> GitHubBootstrapManifest:
    """Load and validate a private GitHub bootstrap manifest."""

    try:
        return GitHubBootstrapManifest.model_validate_json(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise CredentialResolutionError("Could not read GitHub bootstrap manifest.") from exc


def _validate_private_key_path(path: Path) -> None:
    if not path.is_file():
        raise CredentialResolutionError("GitHub App private key file does not exist.")
    mode = stat.S_IMODE(path.stat().st_mode)
    if mode & 0o077:
        raise CredentialResolutionError(
            "GitHub App private key file must not be group/world accessible."
        )
