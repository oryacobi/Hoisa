from collections.abc import Sequence
import importlib.util
from pathlib import Path
import subprocess
import sys
from typing import Any
import unittest
from unittest import mock


def load_workflow() -> Any:
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

    def test_approval_signals_are_scoped_to_latest_plan_comment(self) -> None:
        comments = [
            workflow.Comment(
                body=f"{workflow._agent_marker('Codex', 'plan')}\n\nPlan v1",
                author="codex",
                created_at="2026-05-25T10:00:00Z",
            ),
            workflow.Comment(
                body="approved",
                author="oryacobi",
                created_at="2026-05-25T10:01:00Z",
            ),
            workflow.Comment(
                body=f"{workflow._agent_marker('Codex', 'revised plan')}\n\nPlan v2",
                author="codex",
                created_at="2026-05-25T10:02:00Z",
            ),
        ]

        result = workflow.approval_from_comments(comments, ())

        self.assertEqual(result.state, "needs_approval")
        self.assertEqual(result.workflow_stage, workflow.STAGE_PLAN_APPROVAL)
        self.assertIsNone(result.latest_human_signal_at)

    def test_approval_uses_human_signal_after_latest_plan_comment(self) -> None:
        comments = [
            workflow.Comment(
                body="request changes",
                author="oryacobi",
                created_at="2026-05-25T10:01:00Z",
            ),
            workflow.Comment(
                body=f"{workflow._agent_marker('Codex', 'revised plan')}\n\nPlan v2",
                author="codex",
                created_at="2026-05-25T10:02:00Z",
            ),
            workflow.Comment(
                body="request review",
                author="oryacobi",
                created_at="2026-05-25T10:03:00Z",
            ),
        ]

        result = workflow.approval_from_comments(comments, ())

        self.assertEqual(result.state, "review_requested")
        self.assertEqual(result.workflow_stage, workflow.STAGE_PLAN_REVIEW)
        self.assertEqual(result.latest_human_signal_at, "2026-05-25T10:03:00Z")

    def test_identity_label_detection_handles_helper_labels(self) -> None:
        gh = workflow._Gh(
            owner="oryacobi",
            repo_name="Hoisa",
            project_title="Hoisa",
            approval_assignee="oryacobi",
        )

        self.assertTrue(workflow._looks_identity_label_name("Codex-1"))
        self.assertTrue(workflow._looks_identity_label_name("Codex Agent Jane Doe"))
        self.assertFalse(workflow._looks_identity_label_name("type:task"))
        with mock.patch.object(
            gh,
            "_api_json_value",
            return_value={"description": workflow.IDENTITY_LABEL_DESCRIPTION},
        ):
            self.assertTrue(gh._is_identity_label("Jane Doe"))

    def test_replace_identity_label_removes_only_helper_identity_labels(self) -> None:
        gh = workflow._Gh(
            owner="oryacobi",
            repo_name="Hoisa",
            project_title="Hoisa",
            approval_assignee="oryacobi",
        )

        with (
            mock.patch.object(
                gh,
                "_is_identity_label",
                side_effect=lambda label: label in {"Jane Doe", "Codex-1"},
            ),
            mock.patch.object(gh, "remove_issue_label") as remove_issue_label,
            mock.patch.object(gh, "add_identity_label") as add_identity_label,
        ):
            gh.replace_identity_label(
                2,
                ("type:task", "Jane Doe", "Codex-1", "Codex-2"),
                "Codex-2",
            )

        remove_issue_label.assert_has_calls(
            [
                mock.call(2, "Jane Doe"),
                mock.call(2, "Codex-1"),
            ]
        )
        add_identity_label.assert_called_once_with(2, "Codex-2")

    def test_plan_posting_git_path_commits_and_pushes(self) -> None:
        path = Path("docs/agent-plans/2-example.md")
        calls: list[list[str]] = []

        def fake_run(args: Sequence[str]) -> None:
            calls.append(list(args))

        def fake_probe(args: Sequence[str]) -> subprocess.CompletedProcess[bytes]:
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

        def fake_run(command: Sequence[str]) -> None:
            calls.append(list(command))

        def fake_probe(command: Sequence[str]) -> subprocess.CompletedProcess[bytes]:
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

    def test_select_next_issue_uses_policy_service_for_identity_precedence(self) -> None:
        selection = workflow.select_next_issue(
            (
                self._issue_item(1, workflow.STATUS_TODO, workflow.STAGE_PLANNING),
                self._issue_item(
                    9,
                    workflow.STATUS_IN_PROGRESS,
                    workflow.STAGE_IMPLEMENTATION,
                    labels=("type:task", "Codex-1"),
                ),
            ),
            "Codex",
            identity_label="Codex-1",
        )

        self.assertEqual(selection.action, "implement")
        self.assertIsNotNone(selection.issue)
        self.assertEqual(selection.issue.number, 9)
        self.assertEqual(
            selection.reason,
            "Worker identity label has active work in an agent-owned stage.",
        )

    def test_issue_quality_helper_preserves_report_and_summary_shape(self) -> None:
        issue = workflow.IssueItem(
            number=8,
            title="[Task]: Generic evaluator extraction",
            url="https://github.com/example/hoisa/issues/8",
            body=_quality_task_body("scripts/github/agent_workflow.py"),
            labels=("type:task",),
            status="Todo",
            plan_state="Not Planned",
            workflow_stage="Planning",
            review_route="Review Both",
            agent="Codex",
            phase="",
            size="",
            assignees=(),
            linked_pull_requests=(),
            author_association="OWNER",
        )

        report = workflow.issue_quality_report(
            issue,
            (
                {
                    "id": 123,
                    "body": "> gh api repos/example/project",
                    "authorAssociation": "OWNER",
                },
            ),
        )
        payload = workflow.issue_quality_report_to_json(report)
        summary = workflow.issue_quality_summary_to_json(report)

        self.assertEqual(payload["type"], "task")
        self.assertEqual(payload["risk_level"], "high")
        self.assertIn("path:workflow-helper", payload["risk_reasons"])
        self.assertEqual(
            payload["trust_warnings"][0]["code"],
            "quoted-or-embedded-action-request",
        )
        self.assertEqual(payload["trust_warnings"][0]["source"], "comment:123")
        self.assertEqual(summary["risk_level"], "high")
        self.assertEqual(summary["trust_warning_count"], 1)

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

    def _issue_item(
        self,
        number: int,
        status: str,
        workflow_stage: str,
        *,
        labels: tuple[str, ...] = ("type:task",),
    ) -> Any:
        return workflow.IssueItem(
            number=number,
            title=f"Issue {number}",
            url=f"https://example.invalid/issues/{number}",
            body="## Goal\n\nDo work.\n\n## Acceptance criteria\n\n- Done.",
            labels=labels,
            status=status,
            plan_state=workflow.PLAN_NOT_PLANNED,
            agent="Codex",
            phase="",
            size="",
            assignees=(),
            linked_pull_requests=(),
            workflow_stage=workflow_stage,
            review_route=workflow.REVIEW_ROUTE_HUMAN_ONLY,
        )


def _quality_task_body(extra: str) -> str:
    return f"""## Goal

Make a generic public-safe behavior available.

## Context and likely files

{extra}

## Acceptance criteria

- [ ] Behavior is covered.

## Out of scope

- No private repository content.

## Required checks

- Relevant unit tests.
"""


if __name__ == "__main__":
    unittest.main()
