import ast
from collections.abc import Iterable, Iterator, Sequence
from dataclasses import dataclass
from pathlib import Path
import tomllib
from typing import Any, cast

PROJECT_ROOT = Path(__file__).resolve().parents[3]
SRC_ROOT = PROJECT_ROOT / "src"
PACKAGE_ROOT = SRC_ROOT / "hoisa"
STATIC_RULE_ROOTS = (
    PROJECT_ROOT / "scripts",
    PROJECT_ROOT / "src",
    PROJECT_ROOT / "tests",
)

GITHUB_CLIENT_IMPORTS = frozenset({"github", "github3", "ghapi"})
PYMONGO_IMPORTS = frozenset({"pymongo", "motor"})


@dataclass(frozen=True)
class ImportEdge:
    file: Path
    module: str
    line: int


REQUIRED_PACKAGE_PATHS = (
    PACKAGE_ROOT / "__init__.py",
    PACKAGE_ROOT / "py.typed",
    PACKAGE_ROOT / "domain" / "__init__.py",
    PACKAGE_ROOT / "app" / "__init__.py",
    PACKAGE_ROOT / "app" / "workflows" / "__init__.py",
    PACKAGE_ROOT / "ports" / "__init__.py",
    PACKAGE_ROOT / "adapters" / "__init__.py",
    PACKAGE_ROOT / "adapters" / "external_sources" / "__init__.py",
    PACKAGE_ROOT / "adapters" / "tracker" / "__init__.py",
    PACKAGE_ROOT / "adapters" / "persistence" / "__init__.py",
    PACKAGE_ROOT / "adapters" / "filesystem" / "__init__.py",
    PACKAGE_ROOT / "adapters" / "runner" / "__init__.py",
    PACKAGE_ROOT / "service" / "__init__.py",
    PACKAGE_ROOT / "cli" / "__init__.py",
    PACKAGE_ROOT / "cli" / "commands" / "__init__.py",
    PACKAGE_ROOT / "schemas" / "__init__.py",
    PACKAGE_ROOT / "schemas" / "public" / "__init__.py",
    PACKAGE_ROOT / "privacy" / "__init__.py",
)


def test_required_package_skeleton_exists() -> None:
    missing = [path for path in REQUIRED_PACKAGE_PATHS if not path.exists()]

    assert not missing, "Missing package skeleton paths:\n" + "\n".join(
        _display(path) for path in missing
    )


def test_domain_imports_no_infrastructure_or_interfaces() -> None:
    _assert_no_forbidden_imports(
        PACKAGE_ROOT / "domain",
        {
            "hoisa.adapters",
            "hoisa.service",
            "hoisa.cli",
            *PYMONGO_IMPORTS,
            *GITHUB_CLIENT_IMPORTS,
        },
    )


def test_application_imports_domain_and_ports_not_concrete_adapters() -> None:
    _assert_no_forbidden_imports(
        PACKAGE_ROOT / "app",
        {
            "hoisa.adapters",
            "hoisa.service",
            "hoisa.cli",
            *PYMONGO_IMPORTS,
            *GITHUB_CLIENT_IMPORTS,
        },
    )


def test_application_workflows_exercise_domain_and_port_boundary() -> None:
    edges = tuple(_imports_under(PACKAGE_ROOT / "app" / "workflows"))
    modules = {edge.module for edge in edges}

    assert _imports_any(modules, {"hoisa.domain"}), (
        "Expected at least one application workflow to depend on hoisa.domain."
    )
    assert _imports_any(modules, {"hoisa.ports"}), (
        "Expected at least one application workflow to depend on hoisa.ports."
    )


def test_ports_do_not_import_adapters_or_runtime_surfaces() -> None:
    _assert_no_forbidden_imports(
        PACKAGE_ROOT / "ports",
        {
            "hoisa.adapters",
            "hoisa.service",
            "hoisa.cli",
            *PYMONGO_IMPORTS,
            *GITHUB_CLIENT_IMPORTS,
        },
    )


def test_tooling_includes_src_package() -> None:
    pyproject = _load_pyproject()

    assert "src" in _string_list(pyproject, "tool", "ruff", "src")
    assert "src" in _string_list(pyproject, "tool", "mypy", "files")


def test_python_annotations_do_not_hide_dependencies() -> None:
    violations = [
        violation
        for path in _project_python_files()
        for violation in _annotation_boundary_violations(path)
    ]

    assert not violations, "Forbidden annotation dependency patterns:\n" + "\n".join(violations)


def _assert_no_forbidden_imports(root: Path, forbidden_prefixes: Iterable[str]) -> None:
    forbidden = frozenset(forbidden_prefixes)
    violations = [
        f"{_display(edge.file)}:{edge.line} imports {edge.module}"
        for edge in _imports_under(root)
        if _imports_any({edge.module}, forbidden)
    ]

    assert not violations, "Forbidden architecture imports:\n" + "\n".join(violations)


def _imports_under(root: Path) -> Iterator[ImportEdge]:
    for path in sorted(root.rglob("*.py")):
        yield from _imports_in_file(path)


def _project_python_files() -> Iterator[Path]:
    for root in STATIC_RULE_ROOTS:
        for path in sorted(root.rglob("*.py")):
            if "__pycache__" not in path.parts:
                yield path


def _annotation_boundary_violations(path: Path) -> Iterator[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    typing_aliases: set[str] = set()

    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            if node.module == "__future__":
                for alias in node.names:
                    if alias.name == "annotations":
                        yield f"{_display(path)}:{node.lineno} imports __future__.annotations"
            elif node.module == "typing":
                for alias in node.names:
                    if alias.name == "TYPE_CHECKING":
                        yield f"{_display(path)}:{node.lineno} imports typing.TYPE_CHECKING"
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "typing":
                    typing_aliases.add(alias.asname or alias.name)
        elif isinstance(node, ast.Name) and node.id == "TYPE_CHECKING":
            yield f"{_display(path)}:{node.lineno} references TYPE_CHECKING"
        elif (
            isinstance(node, ast.Attribute)
            and node.attr == "TYPE_CHECKING"
            and isinstance(node.value, ast.Name)
            and node.value.id in typing_aliases
        ):
            yield f"{_display(path)}:{node.lineno} references {node.value.id}.TYPE_CHECKING"


def _imports_in_file(path: Path) -> Iterator[ImportEdge]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                yield ImportEdge(path, alias.name, node.lineno)
        elif isinstance(node, ast.ImportFrom):
            for module in _import_from_modules(path, node):
                yield ImportEdge(path, module, node.lineno)


def _import_from_modules(path: Path, node: ast.ImportFrom) -> Iterator[str]:
    if node.level == 0:
        if node.module is None:
            return
        yield from _base_and_alias_modules(node.module, node.names)
        return

    package_parts = _current_package_parts(path)
    keep_count = max(len(package_parts) - node.level + 1, 0)
    base_parts = package_parts[:keep_count]
    if node.module is not None:
        base_parts.extend(node.module.split("."))

    base_module = ".".join(base_parts)
    yield from _base_and_alias_modules(base_module, node.names)


def _base_and_alias_modules(base_module: str, aliases: Sequence[ast.alias]) -> Iterator[str]:
    if base_module:
        yield base_module
    for alias in aliases:
        if alias.name == "*":
            continue
        yield f"{base_module}.{alias.name}" if base_module else alias.name


def _current_package_parts(path: Path) -> list[str]:
    module_parts = list(path.relative_to(SRC_ROOT).with_suffix("").parts)
    if path.name == "__init__.py":
        return module_parts[:-1]
    return module_parts[:-1]


def _imports_any(modules: Iterable[str], prefixes: Iterable[str]) -> bool:
    return any(
        module == prefix or module.startswith(f"{prefix}.")
        for module in modules
        for prefix in prefixes
    )


def _load_pyproject() -> dict[str, Any]:
    with (PROJECT_ROOT / "pyproject.toml").open("rb") as file:
        return tomllib.load(file)


def _string_list(config: dict[str, Any], *keys: str) -> list[str]:
    current: Any = config
    for key in keys:
        if not isinstance(current, dict):
            raise AssertionError(f"Expected TOML table before {key!r}.")
        current = current[key]

    if not isinstance(current, list) or not all(isinstance(item, str) for item in current):
        raise AssertionError(f"Expected {'.'.join(keys)} to be a list of strings.")
    return cast(list[str], current)


def _display(path: Path) -> str:
    return path.relative_to(PROJECT_ROOT).as_posix()
