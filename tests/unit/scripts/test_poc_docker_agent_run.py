from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
import importlib.util
from pathlib import Path
import subprocess
import sys
from typing import Any

from bson import ObjectId
from pytest import MonkeyPatch

from hoisa.domain.privacy import PublicSafetyClass
from hoisa.domain.runs import RunStatus


def load_poc() -> Any:
    path = Path(__file__).parents[3] / "scripts" / "poc_docker_agent_run.py"
    spec = importlib.util.spec_from_file_location("poc_docker_agent_run", path)
    if spec is None or spec.loader is None:
        raise AssertionError("Could not load Docker POC helper.")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


poc = load_poc()


def test_raw_result_payload_uses_json_scalars_and_iso_datetimes() -> None:
    result = _result(stdout="private stdout", stderr="private stderr")

    payload = poc.raw_result_payload(result)

    assert payload == {
        "image": "hoisa-codex-poc:local",
        "command": "codex --version",
        "network": "none",
        "timeout_seconds": 60,
        "exit_code": 0,
        "stdout": "private stdout",
        "stderr": "private stderr",
        "timed_out": False,
        "started_at": "2026-06-21T12:00:00+00:00",
        "completed_at": "2026-06-21T12:00:02+00:00",
    }
    assert all(
        value is None or isinstance(value, str | int | float | bool) for value in payload.values()
    )


def test_agent_run_summary_excludes_raw_output_and_event_stores_it() -> None:
    result = _result(stdout="private stdout", stderr="private stderr")
    work_item_id = ObjectId("650000000000000000000031")
    run_id = ObjectId("650000000000000000000032")

    run = poc.agent_run_from_result(result, work_item_id=work_item_id, agent_id="codex")
    event = poc.raw_result_event_from_result(result, run_id=run_id, agent_id="codex")

    assert run.status == RunStatus.COMPLETED
    assert run.public_safety == PublicSafetyClass.PRIVATE_REFERENCE
    assert run.command_summaries[0].summary == "Docker Codex POC command completed successfully."
    assert "private stdout" not in run.command_summaries[0].summary
    assert "private stderr" not in run.command_summaries[0].summary
    assert event.subject.subject_type == "agent_run"
    assert event.subject.subject_id == run_id
    assert event.correlation_id == str(run_id)
    assert event.payload_schema == poc.RAW_RESULT_PAYLOAD_SCHEMA
    assert event.payload["stdout"] == "private stdout"
    assert event.payload["stderr"] == "private stderr"
    assert event.public_safety == PublicSafetyClass.PRIVATE_REFERENCE


def test_result_summary_reports_failure_and_timeout_without_raw_output() -> None:
    failed = _result(exit_code=2, stdout="failure stdout", stderr="failure stderr")
    timed_out = _result(
        exit_code=124, stdout="timeout stdout", stderr="timeout stderr", timed_out=True
    )

    failed_run = poc.agent_run_from_result(
        failed,
        work_item_id=ObjectId("650000000000000000000033"),
        agent_id="codex",
    )
    timeout_run = poc.agent_run_from_result(
        timed_out,
        work_item_id=ObjectId("650000000000000000000034"),
        agent_id="codex",
    )

    assert failed_run.status == RunStatus.FAILED
    assert failed_run.command_summaries[0].summary == "Docker Codex POC command exited with 2."
    assert "failure stdout" not in failed_run.command_summaries[0].summary
    assert timeout_run.status == RunStatus.FAILED
    assert (
        timeout_run.command_summaries[0].summary == "Docker Codex POC timed out after 60 seconds."
    )
    assert "timeout stderr" not in timeout_run.command_summaries[0].summary


def test_run_docker_agent_constructs_expected_docker_command(monkeypatch: MonkeyPatch) -> None:
    calls: list[tuple[list[str], dict[str, Any]]] = []

    def fake_run(command: Sequence[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        calls.append((list(command), kwargs))
        return subprocess.CompletedProcess(
            list(command),
            returncode=7,
            stdout="stdout text",
            stderr="stderr text",
        )

    monkeypatch.setattr(poc.subprocess, "run", fake_run)

    result = poc.run_docker_agent(
        image="hoisa-codex-poc:local",
        agent_command="codex --version",
        network="none",
        container_workdir="/workspace",
        env=("CODEX_HOME=/codex-home",),
        volumes=("/host/repo:/workspace:ro",),
        timeout_seconds=12,
    )

    assert calls == [
        (
            [
                "docker",
                "run",
                "--rm",
                "--network",
                "none",
                "--env",
                "CODEX_HOME=/codex-home",
                "--volume",
                "/host/repo:/workspace:ro",
                "--workdir",
                "/workspace",
                "--entrypoint",
                "sh",
                "hoisa-codex-poc:local",
                "-lc",
                "codex --version",
            ],
            {"capture_output": True, "check": False, "text": True, "timeout": 12},
        )
    ]
    assert result.exit_code == 7
    assert result.stdout == "stdout text"
    assert result.stderr == "stderr text"
    assert result.timed_out is False


def test_run_docker_agent_records_timeout_payload(monkeypatch: MonkeyPatch) -> None:
    def fake_timeout(command: Sequence[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        raise subprocess.TimeoutExpired(
            cmd=list(command),
            timeout=kwargs["timeout"],
            output=b"partial stdout",
            stderr=b"partial stderr",
        )

    monkeypatch.setattr(poc.subprocess, "run", fake_timeout)

    result = poc.run_docker_agent(
        image="hoisa-codex-poc:local",
        agent_command="sleep 99",
        network="none",
        container_workdir="",
        env=(),
        volumes=(),
        timeout_seconds=1,
    )

    assert result.exit_code == 124
    assert result.stdout == "partial stdout"
    assert result.stderr == "partial stderr"
    assert result.timed_out is True


def _result(
    *,
    exit_code: int = 0,
    stdout: str = "",
    stderr: str = "",
    timed_out: bool = False,
) -> Any:
    started_at = datetime(2026, 6, 21, 12, 0, tzinfo=UTC)
    return poc.DockerAgentResult(
        image="hoisa-codex-poc:local",
        command="codex --version",
        network="none",
        timeout_seconds=60,
        exit_code=exit_code,
        stdout=stdout,
        stderr=stderr,
        timed_out=timed_out,
        started_at=started_at,
        completed_at=started_at + timedelta(seconds=2),
    )
