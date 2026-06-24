# Flow Catalog

Hoisa flow definitions are repo-defined presets. An agent may choose a flow for
free-text human direction, but Hoisa code validates the selected flow, enforces
allowed transitions, records evidence, and gates human authority.

At first, the catalog contains only:

- `coding_feature`: default flow for normal software implementation work.
- `research_report`: flow for source research, report drafting, and claim
  verification.

Each flow lives in its own directory with a `flow.json` definition.
