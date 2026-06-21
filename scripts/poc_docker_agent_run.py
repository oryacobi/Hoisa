#!/usr/bin/env python3
"""Run a tiny Docker agent command and persist its raw result in MongoDB."""

import argparse
import asyncio
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
import json
import os
from pathlib import Path
import subprocess
import sys
from typing import Any

from bson import ObjectId

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from hoisa.adapters.persistence.antonic import HoisaAntConnector  # noqa: E402
from hoisa.domain.actors import ActorRef, ActorType  # noqa: E402
from hoisa.domain.events import EventSubject, JsonScalar, WorkflowEvent  # noqa: E402
from hoisa.domain.privacy import PublicSafetyClass, RedactionStatus  # noqa: E402
from hoisa.domain.provenance import SourceProvenance, SourceSystem  # noqa: E402
from hoisa.domain.runs import (  # noqa: E402
    AgentRun,
    CommandSummary,
    RunBudget,
    RunnerProfile,
    RunStatus,
)
from hoisa.domain.workflow_event_types import WorkflowEventType  # noqa: E402
from hoisa.domain.workflow_state import RiskLevel, WorkflowStage  # noqa: E402

DEFAULT_IMAGE = "alpine:3.20"
DEFAULT_AGENT_COMMAND = 'printf \'{"agent":"docker-poc","result":"hello from docker"}\\n\''


@dataclass(frozen=True)
class DockerAgentResult:
    """Raw process result from the disposable agent container."""

    image: str
    command: str
    network: str
    timeout_seconds: int
    exit_code: int
    stdout: str
    stderr: str
    timed_out: bool
    started_at: datetime
    completed_at: datetime


async def run_poc(args: argparse.Namespace) -> dict[str, JsonScalar]:
    """Run the container, persist the run and raw event, and read them back."""

    mongo_uri = _mongodb_uri(args)
    database = _database(args)
    result = run_docker_agent(
        image=args.image,
        agent_command=args.agent_command,
        network=args.network,
        container_workdir=args.container_workdir,
        env=args.env,
        volumes=args.volume,
        timeout_seconds=args.timeout_seconds,
    )

    connector = HoisaAntConnector(mongo_uri, database=database)
    try:
        await connector.ensure_indexes()
        stored_run = await connector.insert(
            _agent_run(
                result,
                work_item_id=_object_id(args.work_item_id),
                agent_id=args.agent_id,
            )
        )
        run_id = _required_id(stored_run.id, "inserted AgentRun")
        stored_event = await connector.append_event(
            _raw_result_event(result, run_id=run_id, agent_id=args.agent_id)
        )
        event_id = _required_id(stored_event.id, "inserted raw-result event")

        read_run = await connector.get(AgentRun, run_id)
        read_event = await connector.get(WorkflowEvent, event_id)
        if read_run is None or read_event is None:
            raise RuntimeError("Mongo insert succeeded but read-back failed.")

        payload_matched = read_event.payload == raw_result_payload(result)
        return {
            "agent_run_id": str(run_id),
            "raw_result_event_id": str(event_id),
            "database": database,
            "agent_exit_code": result.exit_code,
            "raw_payload_read_back": payload_matched,
            "stdout": result.stdout if args.print_raw else "",
            "stderr": result.stderr if args.print_raw else "",
        }
    finally:
        await connector.close()


def run_docker_agent(
    *,
    image: str,
    agent_command: str,
    network: str,
    container_workdir: str,
    env: Sequence[str],
    volumes: Sequence[str],
    timeout_seconds: int,
) -> DockerAgentResult:
    """Run one shell command in a throwaway Docker container."""

    started_at = _now()
    docker_command = [
        "docker",
        "run",
        "--rm",
        "--network",
        network,
    ]
    for value in env:
        docker_command.extend(("--env", value))
    for value in volumes:
        docker_command.extend(("--volume", value))
    if container_workdir:
        docker_command.extend(("--workdir", container_workdir))
    docker_command.extend(("--entrypoint", "sh", image, "-lc", agent_command))
    try:
        completed = subprocess.run(  # noqa: S603 - Docker execution is the POC boundary.
            docker_command,
            capture_output=True,
            check=False,
            text=True,
            timeout=timeout_seconds,
        )
        return DockerAgentResult(
            image=image,
            command=agent_command,
            network=network,
            timeout_seconds=timeout_seconds,
            exit_code=completed.returncode,
            stdout=completed.stdout,
            stderr=completed.stderr,
            timed_out=False,
            started_at=started_at,
            completed_at=_now(),
        )
    except subprocess.TimeoutExpired as exc:
        return DockerAgentResult(
            image=image,
            command=agent_command,
            network=network,
            timeout_seconds=timeout_seconds,
            exit_code=124,
            stdout=_output_text(exc.stdout),
            stderr=_output_text(exc.stderr),
            timed_out=True,
            started_at=started_at,
            completed_at=_now(),
        )


def raw_result_payload(result: DockerAgentResult) -> dict[str, JsonScalar]:
    """Return the exact scalar payload stored on the workflow event."""

    return {
        "image": result.image,
        "command": result.command,
        "network": result.network,
        "timeout_seconds": result.timeout_seconds,
        "exit_code": result.exit_code,
        "stdout": result.stdout,
        "stderr": result.stderr,
        "timed_out": result.timed_out,
        "started_at": result.started_at.isoformat(),
        "completed_at": result.completed_at.isoformat(),
    }


def _agent_run(result: DockerAgentResult, *, work_item_id: ObjectId, agent_id: str) -> AgentRun:
    return AgentRun(
        work_item_id=work_item_id,
        workflow_stage=WorkflowStage.IMPLEMENTATION,
        runner_profile=RunnerProfile(
            runner_type="docker",
            profile_name=result.image,
            sandbox="docker",
            network_access=result.network != "none",
        ),
        budget=RunBudget(max_minutes=max(1, (result.timeout_seconds + 59) // 60), max_attempts=1),
        agent=ActorRef(
            actor_type=ActorType.AGENT,
            actor_id=agent_id,
            display_name="Docker POC Agent",
        ),
        status=RunStatus.COMPLETED if result.exit_code == 0 else RunStatus.FAILED,
        started_at=result.started_at,
        completed_at=result.completed_at,
        command_summaries=(
            CommandSummary(
                command_label="docker-agent",
                exit_code=result.exit_code,
                summary=_result_summary(result),
            ),
        ),
        source_provenance=_provenance(result),
        public_safety=PublicSafetyClass.PRIVATE_REFERENCE,
        redaction_status=RedactionStatus.NOT_REQUIRED,
    )


def _raw_result_event(
    result: DockerAgentResult, *, run_id: ObjectId, agent_id: str
) -> WorkflowEvent:
    return WorkflowEvent(
        event_type=WorkflowEventType.AGENT_RUN_COMPLETED,
        happened_at=result.completed_at,
        actor=ActorRef(
            actor_type=ActorType.AGENT,
            actor_id=agent_id,
            display_name="Docker POC Agent",
        ),
        subject=EventSubject(subject_type="agent_run", subject_id=run_id),
        correlation_id=str(run_id),
        workflow_stage=WorkflowStage.IMPLEMENTATION,
        risk=RiskLevel.LOW,
        public_safety=PublicSafetyClass.PRIVATE_REFERENCE,
        payload_schema="poc.docker_agent.raw_result.v1",
        payload=raw_result_payload(result),
        source_provenance=_provenance(result),
        redaction_status=RedactionStatus.NOT_REQUIRED,
    )


def _provenance(result: DockerAgentResult) -> SourceProvenance:
    return SourceProvenance(
        source_system=SourceSystem.RUNNER,
        source_id=f"docker:{result.image}",
        observed_at=result.completed_at,
        public_safety=PublicSafetyClass.PRIVATE_REFERENCE,
    )


def _result_summary(result: DockerAgentResult) -> str:
    if result.timed_out:
        return f"Docker agent timed out after {result.timeout_seconds} seconds."
    if result.exit_code == 0:
        return "Docker agent command completed successfully."
    return f"Docker agent command exited with {result.exit_code}."


def _mongodb_uri(args: argparse.Namespace) -> str:
    uri = args.mongodb_uri or os.environ.get("MONGODB_URI") or _dotenv_value("MONGODB_URI")
    if uri:
        return uri
    raise RuntimeError("Set MONGODB_URI or pass --mongodb-uri for the POC Mongo connection.")


def _database(args: argparse.Namespace) -> str:
    return (
        args.database
        or os.environ.get("MONGODB_DATABASE")
        or os.environ.get("HOISA_MONGO_DATABASE")
        or _dotenv_value("MONGODB_DATABASE")
        or _dotenv_value("HOISA_MONGO_DATABASE")
        or "hoisa"
    )


def _dotenv_value(name: str) -> str:
    dotenv_path = PROJECT_ROOT / "deploy" / "local" / ".env"
    if not dotenv_path.exists():
        return ""
    for line in dotenv_path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        if key.strip() == name:
            return value.strip().strip("'\"")
    return ""


def _object_id(value: str | None) -> ObjectId:
    if value:
        return ObjectId(value)
    return ObjectId()


def _required_id(value: Any, label: str) -> ObjectId:
    if isinstance(value, ObjectId):
        return value
    raise RuntimeError(f"{label} did not receive a Mongo ObjectId.")


def _output_text(value: str | bytes | None) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value


def _now() -> datetime:
    return datetime.now(UTC)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mongodb-uri")
    parser.add_argument("--database")
    parser.add_argument("--image", default=os.environ.get("HOISA_POC_AGENT_IMAGE", DEFAULT_IMAGE))
    parser.add_argument(
        "--agent-command",
        default=os.environ.get("HOISA_POC_AGENT_COMMAND", DEFAULT_AGENT_COMMAND),
        help="Shell command executed inside the container.",
    )
    parser.add_argument("--agent-id", default="docker-poc-agent")
    parser.add_argument("--work-item-id")
    parser.add_argument("--network", default="none")
    parser.add_argument("--container-workdir", default="")
    parser.add_argument("--env", action="append", default=[])
    parser.add_argument("--volume", action="append", default=[])
    parser.add_argument("--timeout-seconds", type=int, default=60)
    parser.add_argument("--print-raw", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        payload = asyncio.run(run_poc(args))
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, indent=2, sort_keys=True))
        return 1

    print(json.dumps({"ok": True, **payload}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
