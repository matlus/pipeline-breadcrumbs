"""The scope tree: where a step runs, logs and emits artifacts.

    PipelineRun -> WorkItemScope -> StepScope -> child StepScope ...

A scope travels as an argument. It replaces the logger, the artifact callback, the work
item and the step number that every step used to receive separately, and it is never
stored on a long-lived object.

A scope holds only what its own lifetime needs: when it was entered and, for a step, the
outcome the step reports. What happened is handed to the run recorder as immutable events.
"""

import logging
from collections.abc import Mapping
from types import TracebackType
from typing import Final, Protocol, Self, final
from uuid import uuid4

from pipeline_breadcrumbs.artifacts import ArtifactKind, StepArtifact
from pipeline_breadcrumbs.attributes import AttributeBag, AttributeKey, AttributeValue, EventKind, detail_key
from pipeline_breadcrumbs.errors import (
    FAILED_AT_STEP_KEY_KEY,
    FAILED_AT_STEP_NAME_KEY,
    FAILED_AT_STEP_NUMBER_KEY,
    ContextualExceptionProtocol,
)
from pipeline_breadcrumbs.formatting import format_byte_size, format_elapsed
from pipeline_breadcrumbs.manifest import ArtifactRecord, ArtifactRecorded, StepClosed, StepRecord, StepRecorded, WorkItemClosed, WorkItemOpened
from pipeline_breadcrumbs.run_context import RunContext
from pipeline_breadcrumbs.steps import Step, StepPath, StepStatus
from pipeline_breadcrumbs.work_items import WorkItem

_MAX_FAILURE_MESSAGE_LENGTH: Final[int] = 500
_ELAPSED_SECONDS_DECIMALS: Final[int] = 3


class StepHostProtocol(Protocol):
    """Anything a step can be opened on: a work item scope, or another step.

    A reusable engine accepts a `StepHostProtocol` and opens its own steps on it, so the same
    engine runs as a whole pipeline or nested inside another step, with its step numbers
    composing automatically (a step 2 inside step 3 reads 3.2 everywhere).
    """

    def step(self, step: Step) -> StepScope: ...

    def skipped(self, step: Step, reason: str) -> None: ...


def _detail_attributes(fields: Mapping[str, AttributeValue]) -> AttributeBag:
    detail_attributes: AttributeBag = {}
    field_name: str
    field_value: AttributeValue
    for field_name, field_value in fields.items():
        detail_attributes[detail_key(field_name)] = field_value
    return detail_attributes


def _failure_message(error: BaseException) -> str:
    text: str = str(error).strip() or type(error).__name__
    return text if len(text) <= _MAX_FAILURE_MESSAGE_LENGTH else f"{text[:_MAX_FAILURE_MESSAGE_LENGTH]}..."


@final
class WorkItemScope:
    """One work item's journey through the pipeline. Open it with `async with`."""

    def __init__(self, run_context: RunContext, work_item: WorkItem) -> None:
        self._run_context: RunContext = run_context
        self._work_item: WorkItem = work_item
        self._started: float = 0.0
        self._attributes: AttributeBag = {
            AttributeKey.WORK_ITEM_ID: work_item.id,
            AttributeKey.WORK_ITEM_NAME: work_item.name,
        }

    @property
    def work_item(self) -> WorkItem:
        return self._work_item

    @property
    def attributes(self) -> AttributeBag:
        return dict(self._attributes)

    async def __aenter__(self) -> Self:
        self._started = self._run_context.clock.monotonic()
        self._run_context.run_recorder.record(
            WorkItemOpened(
                work_item_id=self._work_item.id,
                work_item_name=self._work_item.name,
                started_at=self._run_context.clock.now().isoformat(),
            )
        )
        self._run_context.log(
            logging.INFO,
            f"Work item {self._work_item.name} started",
            self._boundary_attributes(StepStatus.STARTED),
        )
        return self

    async def __aexit__(self, _exc_type: type[BaseException] | None, exc: BaseException | None, _traceback: TracebackType | None) -> None:
        elapsed_seconds: float = self._run_context.clock.monotonic() - self._started
        if exc is None:
            self._complete(elapsed_seconds)
            return
        self._fail(elapsed_seconds, exc)

    def step(self, step: Step) -> StepScope:
        """Open a top-level step of the pipeline on this work item."""
        return StepScope(self._run_context, self, StepPath().child(step.step_number), step)

    def skipped(self, step: Step, reason: str) -> None:
        """Record that a top-level step did not run, and why."""
        _record_skipped(self._run_context, self, StepPath().child(step.step_number), step, reason)

    def _complete(self, elapsed_seconds: float) -> None:
        self._run_context.run_recorder.record(
            WorkItemClosed(
                work_item_id=self._work_item.id,
                work_item_status=StepStatus.COMPLETE,
                elapsed_seconds=elapsed_seconds,
                failure=None,
            )
        )
        attributes: AttributeBag = self._boundary_attributes(StepStatus.COMPLETE)
        attributes[AttributeKey.ELAPSED_SECONDS] = round(elapsed_seconds, _ELAPSED_SECONDS_DECIMALS)
        self._run_context.log(logging.INFO, f"Work item {self._work_item.name} complete in {format_elapsed(elapsed_seconds)}", attributes)

    def _fail(self, elapsed_seconds: float, exc: BaseException) -> None:
        self._run_context.run_recorder.record(
            WorkItemClosed(
                work_item_id=self._work_item.id,
                work_item_status=StepStatus.FAILED,
                elapsed_seconds=elapsed_seconds,
                failure=f"{type(exc).__name__}: {_failure_message(exc)}",
            )
        )
        attributes: AttributeBag = self._boundary_attributes(StepStatus.FAILED)
        attributes[AttributeKey.ELAPSED_SECONDS] = round(elapsed_seconds, _ELAPSED_SECONDS_DECIMALS)
        attributes[AttributeKey.FAILURE_TYPE] = type(exc).__name__
        attributes[AttributeKey.FAILURE_MESSAGE] = _failure_message(exc)
        self._run_context.log(logging.WARNING, f"Work item {self._work_item.name} failed after {format_elapsed(elapsed_seconds)}", attributes)

    def _boundary_attributes(self, work_item_status: StepStatus) -> AttributeBag:
        return {
            **self._attributes,
            AttributeKey.EVENT: EventKind.WORK_ITEM,
            AttributeKey.STATUS: work_item_status.value,
        }


def _step_attributes(work_item_scope: WorkItemScope, step_path: StepPath, step: Step) -> AttributeBag:
    return {
        **work_item_scope.attributes,
        AttributeKey.STEP_NUMBER: str(step_path),
        AttributeKey.STEP_NAME: step.name,
        AttributeKey.STEP_KEY: step.key,
    }


def _record_skipped(run_context: RunContext, work_item_scope: WorkItemScope, step_path: StepPath, step: Step, reason: str) -> None:
    run_context.run_recorder.record(
        StepRecorded(
            work_item_id=work_item_scope.work_item.id,
            step_instance_id=uuid4().hex,
            step_record=StepRecord(
                path=str(step_path),
                key=step.key,
                name=step.name,
                step_status=StepStatus.SKIPPED,
                started_at=run_context.clock.now().isoformat(),
                outcome=reason,
            ),
        )
    )
    attributes: AttributeBag = _step_attributes(work_item_scope, step_path, step)
    attributes[AttributeKey.EVENT] = EventKind.STEP
    attributes[AttributeKey.STATUS] = StepStatus.SKIPPED.value
    attributes[AttributeKey.OUTCOME] = reason
    run_context.log(logging.INFO, f"Step {step_path} {step.name} skipped: {reason}", attributes)


@final
class StepScope:
    """One step. Open it with `async with`; it announces itself, times itself and reports how it ended.

    Inside the step, `info` and `warning` write progress lines, `outcome` sets the closing
    summary, `emit` hands an artifact to the host's sink, and `step` opens a child step.
    """

    def __init__(self, run_context: RunContext, work_item_scope: WorkItemScope, step_path: StepPath, step: Step) -> None:
        self._run_context: RunContext = run_context
        self._work_item_scope: WorkItemScope = work_item_scope
        self._step_path: StepPath = step_path
        self._step: Step = step
        self._step_instance_id: str = uuid4().hex
        self._started: float = 0.0
        self._outcome_message: str | None = None
        self._outcome_fields: AttributeBag = {}

    @property
    def step_path(self) -> StepPath:
        return self._step_path

    @property
    def step_definition(self) -> Step:
        return self._step

    async def __aenter__(self) -> Self:
        self._started = self._run_context.clock.monotonic()
        self._run_context.run_recorder.record(
            StepRecorded(
                work_item_id=self._work_item_scope.work_item.id,
                step_instance_id=self._step_instance_id,
                step_record=StepRecord(
                    path=str(self._step_path),
                    key=self._step.key,
                    name=self._step.name,
                    step_status=StepStatus.STARTED,
                    started_at=self._run_context.clock.now().isoformat(),
                ),
            )
        )
        self._run_context.log(
            logging.INFO,
            f"Step {self._step_path} {self._step.name} started",
            self._boundary_attributes(StepStatus.STARTED),
        )
        return self

    async def __aexit__(self, _exc_type: type[BaseException] | None, exc: BaseException | None, _traceback: TracebackType | None) -> None:
        elapsed_seconds: float = self._run_context.clock.monotonic() - self._started
        if exc is None:
            self._complete(elapsed_seconds)
            return
        self._fail(elapsed_seconds, exc)

    def step(self, step: Step) -> StepScope:
        """Open a child step. Its number composes under this step's path."""
        return StepScope(self._run_context, self._work_item_scope, self._step_path.child(step.step_number), step)

    def skipped(self, step: Step, reason: str) -> None:
        """Record that a child step did not run, and why."""
        _record_skipped(self._run_context, self._work_item_scope, self._step_path.child(step.step_number), step, reason)

    def info(self, message: str, /, **fields: AttributeValue) -> None:
        """A progress line. Report counts and identifiers, never payloads."""
        self._log_progress(logging.INFO, message, fields)

    def warning(self, message: str, /, **fields: AttributeValue) -> None:
        self._log_progress(logging.WARNING, message, fields)

    def outcome(self, message: str, /, **fields: AttributeValue) -> None:
        """Set the summary reported when the step completes. The last call wins."""
        self._outcome_message = message
        self._outcome_fields = dict(fields)

    async def emit(self, artifact_kind: ArtifactKind, content: bytes, *, discriminator: str | None = None) -> StepArtifact:
        """Hand an artifact to the host's sink. Returns the artifact so a caller can reference its filename.

        Use `discriminator` (for example `page_0003`) when a step emits one artifact per
        unit of work. Emit raw model output before validating it, so a validation failure
        leaves its evidence on disk.
        """
        step_artifact: StepArtifact = StepArtifact(
            artifact_kind=artifact_kind,
            content=content,
            work_item=self._work_item_scope.work_item,
            step_path=self._step_path,
            discriminator=discriminator,
        )
        await self._run_context.persist(step_artifact)
        self._record_artifact(step_artifact)
        self._log_artifact_emitted(step_artifact)
        return step_artifact

    def _complete(self, elapsed_seconds: float) -> None:
        self._run_context.run_recorder.record(
            StepClosed(
                work_item_id=self._work_item_scope.work_item.id,
                step_instance_id=self._step_instance_id,
                step_status=StepStatus.COMPLETE,
                elapsed_seconds=elapsed_seconds,
                outcome=self._outcome_message,
                failure=None,
            )
        )
        attributes: AttributeBag = self._boundary_attributes(StepStatus.COMPLETE)
        attributes.update(_detail_attributes(self._outcome_fields))
        attributes[AttributeKey.ELAPSED_SECONDS] = round(elapsed_seconds, _ELAPSED_SECONDS_DECIMALS)
        message: str = f"Step {self._step_path} {self._step.name} complete in {format_elapsed(elapsed_seconds)}"
        if self._outcome_message:
            attributes[AttributeKey.OUTCOME] = self._outcome_message
            message = f"{message}: {self._outcome_message}"
        self._run_context.log(logging.INFO, message, attributes)

    def _fail(self, elapsed_seconds: float, exc: BaseException) -> None:
        self._stamp_failing_step_onto(exc)
        failure_text: str = _failure_message(exc)
        self._run_context.run_recorder.record(
            StepClosed(
                work_item_id=self._work_item_scope.work_item.id,
                step_instance_id=self._step_instance_id,
                step_status=StepStatus.FAILED,
                elapsed_seconds=elapsed_seconds,
                outcome=None,
                failure=f"{type(exc).__name__}: {failure_text}",
            )
        )
        attributes: AttributeBag = self._boundary_attributes(StepStatus.FAILED)
        attributes[AttributeKey.ELAPSED_SECONDS] = round(elapsed_seconds, _ELAPSED_SECONDS_DECIMALS)
        attributes[AttributeKey.FAILURE_TYPE] = type(exc).__name__
        attributes[AttributeKey.FAILURE_MESSAGE] = failure_text
        # A failed step is a breadcrumb saying where the run stopped. The exception itself is
        # logged once, with its traceback, by the host's outer boundary, so it is not repeated here.
        self._run_context.log(
            logging.WARNING,
            f"Step {self._step_path} {self._step.name} failed after {format_elapsed(elapsed_seconds)}: {type(exc).__name__}: {failure_text}",
            attributes,
        )

    def _record_artifact(self, step_artifact: StepArtifact) -> None:
        self._run_context.run_recorder.record(
            ArtifactRecorded(
                work_item_id=self._work_item_scope.work_item.id,
                artifact_record=ArtifactRecord(
                    filename=step_artifact.filename,
                    artifact_type=step_artifact.artifact_type,
                    role=step_artifact.artifact_kind.role.value,
                    byte_count=len(step_artifact.content),
                    step_path=str(self._step_path),
                ),
            )
        )

    def _log_artifact_emitted(self, step_artifact: StepArtifact) -> None:
        attributes: AttributeBag = self._attributes()
        attributes[AttributeKey.ARTIFACT_KIND] = step_artifact.artifact_type
        attributes[AttributeKey.ARTIFACT_FILENAME] = step_artifact.filename
        attributes[AttributeKey.ARTIFACT_BYTES] = len(step_artifact.content)
        self._run_context.log(
            logging.INFO,
            f"Emitted artifact: {step_artifact.filename} ({format_byte_size(len(step_artifact.content))})",
            attributes,
        )

    def _attributes(self) -> AttributeBag:
        return _step_attributes(self._work_item_scope, self._step_path, self._step)

    def _boundary_attributes(self, step_status: StepStatus) -> AttributeBag:
        attributes: AttributeBag = self._attributes()
        attributes[AttributeKey.EVENT] = EventKind.STEP
        attributes[AttributeKey.STATUS] = step_status.value
        return attributes

    def _log_progress(self, level: int, message: str, fields: Mapping[str, AttributeValue]) -> None:
        attributes: AttributeBag = self._attributes()
        attributes.update(_detail_attributes(fields))
        self._run_context.log(level, message, attributes)

    def _stamp_failing_step_onto(self, error: BaseException) -> None:
        """Name the step an exception escaped from, once. The innermost step is the failing one."""
        if not isinstance(error, ContextualExceptionProtocol):
            return
        if FAILED_AT_STEP_NUMBER_KEY in error.contextual_data_by_name:
            return
        error.add_contextual_data(
            {
                FAILED_AT_STEP_NUMBER_KEY: str(self._step_path),
                FAILED_AT_STEP_NAME_KEY: self._step.name,
                FAILED_AT_STEP_KEY_KEY: self._step.key,
            }
        )
