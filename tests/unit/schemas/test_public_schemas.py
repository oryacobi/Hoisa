import json
from pathlib import Path
import re
from typing import Any, cast

from hoisa.schemas.public.catalog import PUBLIC_SCHEMAS

PROJECT_ROOT = Path(__file__).resolve().parents[3]
SCHEMA_ROOT = PROJECT_ROOT / "src" / "hoisa" / "schemas" / "public"
FIXTURE_ROOT = PROJECT_ROOT / "tests" / "fixtures" / "public"

PRIVATE_MARKERS = tuple(
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"/Users/",
        r"/home/",
        r"/private/",
        r"[A-Z]:\\\\",
        r"api[_-]?key",
        r"password",
        r"raw[_-]?log",
        r"screenshot",
        r"credential",
    )
)


def test_public_schema_files_match_generated_models() -> None:
    for schema_name, model_type in PUBLIC_SCHEMAS.items():
        schema_path = SCHEMA_ROOT / schema_name

        assert schema_path.exists(), f"Missing public schema file: {schema_name}"
        assert _load_json(schema_path) == _public_schema(model_type.model_json_schema())


def test_public_fixtures_validate_against_catalog_models() -> None:
    for schema_name, model_type in PUBLIC_SCHEMAS.items():
        fixture_name = schema_name.removesuffix(".schema.json") + ".json"
        fixture_path = FIXTURE_ROOT / fixture_name

        assert fixture_path.exists(), f"Missing public fixture file: {fixture_name}"
        model_type.model_validate_json(fixture_path.read_text(encoding="utf-8"))


def test_public_artifacts_do_not_contain_private_markers() -> None:
    scanned_paths = [*SCHEMA_ROOT.glob("*.schema.json"), *FIXTURE_ROOT.glob("*.json")]
    violations = [
        f"{path.relative_to(PROJECT_ROOT).as_posix()} matches {pattern.pattern}"
        for path in scanned_paths
        for pattern in PRIVATE_MARKERS
        if pattern.search(path.read_text(encoding="utf-8"))
    ]

    assert not violations, "Private-looking public artifact content:\n" + "\n".join(violations)


def _load_json(path: Path) -> dict[str, Any]:
    return cast(dict[str, Any], json.loads(path.read_text(encoding="utf-8")))


def _public_schema(schema: dict[str, Any]) -> dict[str, Any]:
    return cast(dict[str, Any], json.loads(json.dumps(schema, indent=2, sort_keys=True)))
