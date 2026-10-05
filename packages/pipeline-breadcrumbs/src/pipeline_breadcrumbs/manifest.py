"""The run manifest: an index of what a run did, written as the run's last artifact.

Read the manifest first. It lists every work item, every step with its status, elapsed
time and outcome, every artifact with its size, and any failure, so the first step
whose output went wrong is findable without opening a single other file.

The recorder keeps an append-only list of immutable events. The manifest is built from them
at the end, so no record is ever edited after it is created.
"""

import json
from collections.abc import Sequence
from dataclasses import asdict, dataclass, replace
from datetime import datetime
from typing import Final, final

from pipeline_breadcrumbs.artifacts import ArtifactKind, ArtifactRole
from pipeline_breadcrumbs.steps import StepStatus

MANIFEST_KIND: Final[ArtifactKind] = ArtifactKind("manifest", "json", "application/json", role=ArtifactRole.OUTPUT)

_ELAPSED_SECONDS_DECIMALS: Final[int] = 3


@final
@dataclass(frozen=True, slots=True)
class StepRecord:
    step_path: str
    step_key: str
    step_name: str
    step_status: StepStatus
    started_at: str
    elapsed_seconds: float | None = None
    outcome: str | None = None
    failure: str | None = None


@final
@dataclass(frozen=True, slots=True)
class ArtifactRecord:
    filename: str
    artifact_type: str
    role: str
    byte_count: int
    step_path: str


@final
@dataclass(frozen=True, slots=True)
class WorkItemRecord:
    work_item_id: str
    work_item_name: str
    work_item_status: StepStatus
    started_at: str
    elapsed_seconds: float | None = None
    failure: str | None = None
    step_records: tuple[StepRecord, ...] = ()
    artifact_records: tuple[ArtifactRecord, ...] = ()


@final
@dataclass(frozen=True, slots=True)
class RunRecord:
    pipeline_name: str
    run_id: str
    run_status: StepStatus
    started_at: str
    finished_at: str
    elapsed_seconds: float
    work_item_records: tuple[WorkItemRecord, ...]


@final
@dataclass(frozen=True, slots=True)
class WorkItemOpened:
    work_item_id: str
    work_item_name: str
    started_at: str


@final
@dataclass(frozen=True, slots=True)
class WorkItemClosed:
    work_item_id: str
    work_item_status: StepStatus
    elapsed_seconds: float
    failure: str | None


@final
@dataclass(frozen=True, slots=True)
class StepRecorded:
    """A step entry was added: opened (still running) or skipped.

    `step_instance_id` tells one opening of a step from another, so a step opened once per page,
    or on several pages at once, keeps one record per opening.
    """

    work_item_id: str
    step_instance_id: str
    step_record: StepRecord


@final
@dataclass(frozen=True, slots=True)
class StepClosed:
    work_item_id: str
    step_instance_id: str
    step_status: StepStatus
    elapsed_seconds: float
    outcome: str | None
    failure: str | None


@final
@dataclass(frozen=True, slots=True)
class ArtifactRecorded:
    work_item_id: str
    artifact_record: ArtifactRecord


type RunEvent = WorkItemOpened | WorkItemClosed | StepRecorded | StepClosed | ArtifactRecorded


def build_work_item_records(run_events: Sequence[RunEvent]) -> tuple[WorkItemRecord, ...]:
    """Fold the run's events into one immutable record per opening of a work item, in the order they were opened.

    A work item id opened more than once (a retry, say) keeps every attempt as its own record, so an
    earlier failure still counts. Later events for that id belong to its latest attempt, so one work
    item id must not run concurrently with itself.
    """
    attempt_work_item_records: list[WorkItemRecord] = []
    step_records_by_step_instance_id_by_attempt: list[dict[str, StepRecord]] = []
    artifact_records: list[list[ArtifactRecord]] = []
    latest_attempt_index_by_work_item_id: dict[str, int] = {}
    for run_event in run_events:
        match run_event:
            case WorkItemOpened():
                latest_attempt_index_by_work_item_id[run_event.work_item_id] = len(attempt_work_item_records)
                attempt_work_item_records.append(
                    WorkItemRecord(
                        work_item_id=run_event.work_item_id,
                        work_item_name=run_event.work_item_name,
                        work_item_status=StepStatus.STARTED,
                        started_at=run_event.started_at,
                    )
                )
                step_records_by_step_instance_id_by_attempt.append({})
                artifact_records.append([])
            case WorkItemClosed():
                attempt_index: int = latest_attempt_index_by_work_item_id[run_event.work_item_id]
                attempt_work_item_records[attempt_index] = replace(
                    attempt_work_item_records[attempt_index],
                    work_item_status=run_event.work_item_status,
                    elapsed_seconds=round(run_event.elapsed_seconds, _ELAPSED_SECONDS_DECIMALS),
                    failure=run_event.failure,
                )
            case StepRecorded():
                step_records_by_step_instance_id_by_attempt[latest_attempt_index_by_work_item_id[run_event.work_item_id]][
                    run_event.step_instance_id
                ] = run_event.step_record
            case StepClosed():
                open_step_records_by_step_instance_id: dict[str, StepRecord] = step_records_by_step_instance_id_by_attempt[
                    latest_attempt_index_by_work_item_id[run_event.work_item_id]
                ]
                open_step_records_by_step_instance_id[run_event.step_instance_id] = replace(
                    open_step_records_by_step_instance_id[run_event.step_instance_id],
                    step_status=run_event.step_status,
                    elapsed_seconds=round(run_event.elapsed_seconds, _ELAPSED_SECONDS_DECIMALS),
                    outcome=run_event.outcome,
                    failure=run_event.failure,
                )
            case ArtifactRecorded():
                artifact_records[latest_attempt_index_by_work_item_id[run_event.work_item_id]].append(run_event.artifact_record)
    completed_work_item_records: list[WorkItemRecord] = []
    attempt_work_item_record: WorkItemRecord
    step_records_by_step_instance_id: dict[str, StepRecord]
    attempt_artifact_records: list[ArtifactRecord]
    for attempt_work_item_record, step_records_by_step_instance_id, attempt_artifact_records in zip(
        attempt_work_item_records, step_records_by_step_instance_id_by_attempt, artifact_records, strict=True
    ):
        completed_work_item_records.append(
            replace(
                attempt_work_item_record,
                step_records=tuple(step_records_by_step_instance_id.values()),
                artifact_records=tuple(attempt_artifact_records),
            )
        )
    return tuple(completed_work_item_records)


@final
class RunRecorder:
    """Collects what happened during a run, as immutable events, for the manifest."""

    def __init__(self, *, pipeline_name: str, run_id: str) -> None:
        self._pipeline_name: str = pipeline_name
        self._run_id: str = run_id
        self._run_events: list[RunEvent] = []

    def record_run_event(self, run_event: RunEvent) -> None:
        self._run_events.append(run_event)

    def work_item_count(self) -> int:
        return len(build_work_item_records(self._run_events))

    def failed_work_item_count(self) -> int:
        return sum(1 for work_item_record in build_work_item_records(self._run_events) if work_item_record.work_item_status is StepStatus.FAILED)

    def serialize_manifest(self, *, started_at: datetime, finished_at: datetime, elapsed_seconds: float, run_status: StepStatus) -> bytes:
        run_record: RunRecord = RunRecord(
            pipeline_name=self._pipeline_name,
            run_id=self._run_id,
            run_status=run_status,
            started_at=started_at.isoformat(),
            finished_at=finished_at.isoformat(),
            elapsed_seconds=round(elapsed_seconds, _ELAPSED_SECONDS_DECIMALS),
            work_item_records=build_work_item_records(self._run_events),
        )
        return json.dumps(asdict(run_record), indent=2).encode("utf-8")
