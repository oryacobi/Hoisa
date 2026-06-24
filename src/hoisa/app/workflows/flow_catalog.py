"""Load predefined flow definitions from the repo flow catalog."""

from pathlib import Path

from hoisa.domain.flow_definitions import FlowDefinition

FLOW_FILE_NAME = "flow.json"


class FlowCatalogError(ValueError):
    """Raised when the checked-in flow catalog is malformed."""


def load_flow_catalog(root: Path) -> dict[str, FlowDefinition]:
    """Load all immediate child flow definitions under a catalog root."""

    flow_paths = sorted(root.glob(f"*/{FLOW_FILE_NAME}"))
    if not flow_paths:
        raise FlowCatalogError(f"No flow definitions found under {root}.")

    catalog: dict[str, FlowDefinition] = {}
    for path in flow_paths:
        flow = FlowDefinition.model_validate_json(path.read_text(encoding="utf-8"))
        directory_id = path.parent.name
        if flow.flow_id != directory_id:
            raise FlowCatalogError(
                f"Flow ID {flow.flow_id!r} does not match directory {directory_id!r}."
            )
        if flow.flow_id in catalog:
            raise FlowCatalogError(f"Duplicate flow ID: {flow.flow_id}.")
        catalog[flow.flow_id] = flow

    return catalog
