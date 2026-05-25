from __future__ import annotations

import importlib.util
from pathlib import Path
import subprocess
import sys
import unittest
from unittest import mock


def load_workflow():
    path = Path(__file__).parents[3] / "scripts" / "github" / "agent_workflow.py"
    spec = importlib.util.spec_from_file_location("agent_workflow", path)
    if spec is None or spec.loader is None:
        raise AssertionError("Could not load agent_workflow helper.")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


workflow = load_workflow()


class AgentWorkflowTests(unittest.TestCase):
    def test_hoisa_defaults_and_marker(self) -> None:
        self.assertEqual(workflow.DEFAULT_OWNER, "oryacobi")
        self.assertEqual(workflow.DEFAULT_REPO_NAME, "Hoisa")
        self.assertEqual(workflow.DEFAULT_PROJECT_TITLE, "Hoisa")
        self.assertEqual(workflow.AGENT_MARKER_PREFIX, "<!-- hoisa-agent:")

    def test_branch_and_plan_path_use_issue_slug(self) -> None:
        title = "[Spike]: Define Hoisa architecture and persistence direction"

        self.assertEqual(
            workflow.branch_name("Codex", 2, title),
            "codex/2-spike-define-hoisa-architecture-and-persistence",
        )
        self.assertEqual(
            workflow.plan_path(2, title).as_posix(),
            "docs/agent-plans/2-spike-define-hoisa-architecture-and-persistence.md",
        )

    def test_workflow_field_bootstrap_covers_project_fields(self) -> None:
        self.assertEqual(
            workflow._missing_workflow_fields({"fields": []}),
            ("Status", "Agent", "Workflow Stage", "Review Route"),
        )

        self.assertEqual(
            [option["name"] for option in workflow._workflow_field_options("Status")],
            ["Todo", "In Progress", "Done"],
        )
        self.assertEqual(
            [option["name"] for option in workflow._workflow_field_options("Agent")],
            ["Codex", "Claude", "Cursor", "Human"],
        )

    def test_plan_posting_git_path_commits_and_pushes(self) -> None:
        path = Path("docs/agent-plans/2-example.md")
        calls: list[list[str]] = []

        def fake_run(args):
            calls.append(list(args))

        def fake_probe(args):
            calls.append(list(args))
            return subprocess.CompletedProcess(["git", *args], 1)

        with (
            mock.patch.object(workflow, "_git_run", side_effect=fake_run),
            mock.patch.object(workflow, "_git_probe", side_effect=fake_probe),
        ):
            workflow._commit_and_push_plan(path, 2, "codex/2-example", revision=False, no_git=False)

        self.assertEqual(
            calls,
            [
                ["add", "docs/agent-plans/2-example.md"],
                ["diff", "--cached", "--quiet", "--", "docs/agent-plans/2-example.md"],
                ["commit", "-m", "Plan issue #2"],
                ["push", "-u", "origin", "codex/2-example"],
            ],
        )

    def test_commit_push_stages_selected_paths_and_pushes_current_branch(self) -> None:
        calls: list[list[str]] = []
        args = type(
            "Args",
            (),
            {
                "issue": 2,
                "message": "Implement issue #2",
                "path": [Path("scripts/github/agent_workflow.py")],
                "all": False,
            },
        )()

        def fake_run(command):
            calls.append(list(command))

        def fake_probe(command):
            calls.append(list(command))
            return subprocess.CompletedProcess(["git", *command], 1)

        with (
            mock.patch.object(workflow, "_current_branch", return_value="codex/2-helper"),
            mock.patch.object(workflow, "_git_run", side_effect=fake_run),
            mock.patch.object(workflow, "_git_probe", side_effect=fake_probe),
        ):
            result = workflow._cmd_commit_push(args)

        self.assertEqual(result["branch"], "codex/2-helper")
        self.assertTrue(result["committed"])
        self.assertEqual(
            calls,
            [
                ["add", "scripts/github/agent_workflow.py"],
                ["diff", "--cached", "--quiet"],
                ["commit", "-m", "Implement issue #2"],
                ["push", "-u", "origin", "codex/2-helper"],
            ],
        )

    def test_no_project_specific_private_terms_remain(self) -> None:
        helper = Path(workflow.__file__).read_text(encoding="utf-8").lower()
        forbidden = (
            "hori" + "zon",
            "inves" + "tments",
            "bro" + "ker",
            "ib" + "kr",
            "market" + "-data",
            "src/" + "horizon",
            "simu" + "lation",
            "not" + "ional",
            "drop" + "-copy",
            "recon" + "ciliation",
        )
        for term in forbidden:
            self.assertNotIn(term, helper)


if __name__ == "__main__":
    unittest.main()
