"""One execution of a pipeline, from its first work item to its manifest."""

import logging
from collections.abc import Mapping
from datetime import datetime
from types import TracebackType
from typing import Final, Self, final
from uuid import uuid4

from pipeline_breadcrumbs.artifact_sink_exceptions import ArtifactSinkException
from pipeline_breadcrumbs.artifacts import ArtifactKind, ArtifactSinkProtocol, RunArtifact
from pipeline_breadcrumbs.attributes import AttributeBag, AttributeKey, AttributeValue, EventKind
from pipeline_breadcrumbs.clock import Clock
from pipeline_breadcrumbs.declaration_exceptions import InvalidDeclarationException
from pipeline_breadcrumbs.formatting import format_byte_size, format_elapsed
from pipeline_breadcrumbs.manifest import MANIFEST_KIND, RunArtifactRecord, RunRecorder
from pipeline_breadcrumbs.run_context import RunContext
from pipeline_breadcrumbs.scopes import WorkItemScope
from pipeline_breadcrumbs.steps import StepStatus
from pipeline_breadcrumbs.work_items import WorkItem

DEFAULT_LOGGER_NAME: Final[str] = "pipeline_breadcrumbs"

# The standard `logging` module refuses an `extra` key that collides with a LogRecord
# attribute. `message` and `asctime` are not on a fresh record but the formatter adds them
# later, so they are reserved here by hand.
_RESERVED_RECORD_ATTRIBUTES: Final[frozenset[str]] = frozenset(
    {*logging.LogRecord("", 0, "", 0, "", (), None).__dict__, "message", "asctime"},
)

_ELAPSED_SECONDS_DECIMALS: Final[int] = 3


@final
class PipelineRun:
    """One execution of a pipeline. Open it with `async with`, then open work items on it.

    The run owns the artifact sink, the logger and the manifest. Closing it logs the run's
    summary and emits `manifest.json` through the same sink as every other artifact.

    `attributes` are merged into every record the run writes. This is the one seam for a
    trace id, a span id or a user name: add it here and every record carries it.
    """

    def __init__(
        self,
        *,
        pipeline_name: str,
        artifact_sink: ArtifactSinkProtocol,
        logger: logging.Logger | None = None,
        attributes: Mapping[str, AttributeValue] | None = None,
        supplied_clock: Clock | None = None,
    ) -> None:
        _require_pipeline_name(pipeline_name)
        caller_attributes: AttributeBag = _validate_caller_attributes(attributes)
        run_clock: Clock = supplied_clock or Clock.create_system_clock()
        self._run_id: str = _create_run_id(run_clock)
        self._pipeline_name: str = pipeline_name
        self._run_context: RunContext = RunContext(
            artifact_sink=artifact_sink,
            logger=logger or logging.getLogger(DEFAULT_LOGGER_NAME),
            base_attributes={
                **caller_attributes,
                AttributeKey.PIPELINE_NAME: pipeline_name,
                AttributeKey.RUN_ID: self._run_id,
            },
            clock=run_clock,
            run_recorder=RunRecorder(pipeline_name=pipeline_name, run_id=self._run_id),
        )
        self._started: float = 0.0
        self._started_at: datetime = run_clock.now()

    @property
    def run_id(self) -> str:
        return self._run_id

    async def __aenter__(self) -> Self:
        self._started = self._run_context.clock.monotonic()
        self._started_at = self._run_context.clock.now()
        self._run_context.log(
            logging.INFO,
            f"Run {self._run_id} of {self._pipeline_name} started",
            self._boundary_attributes(StepStatus.STARTED),
        )
        return self

    async def __aexit__(self, _exc_type: type[BaseException] | None, exc: BaseException | None, _traceback: TracebackType | None) -> None:
        elapsed_seconds: float = self._run_context.clock.monotonic() - self._started
        run_status: StepStatus = self._run_status(exc)
        self._log_run_finished(elapsed_seconds, run_status)
        await self._emit_manifest(elapsed_seconds, run_status, original_error=exc)

    async def emit(self, artifact_kind: ArtifactKind, content: bytes) -> RunArtifact:
        """Hand an artifact that belongs to the whole run, rather than to one step of one work item, to the sink.

        Use it for what the run as a whole was given or decided, such as the settings it ran with. The manifest
        lists it among the run's artifacts. Its filename is the kind's key and extension, so emit each kind once.
        """
        _require_run_artifact_kind(artifact_kind)
        run_artifact: RunArtifact = RunArtifact(artifact_kind=artifact_kind, content=content)
        await self._run_context.persist(run_artifact)
        self._run_context.run_recorder.record_run_artifact(
            RunArtifactRecord(
                filename=run_artifact.filename,
                artifact_type=run_artifact.artifact_type,
                role=artifact_kind.role.value,
                byte_count=len(content),
            )
        )
        self._log_run_artifact_emitted(run_artifact)
        return run_artifact

    def open_work_item(self, work_item: WorkItem) -> WorkItemScope:
        """The returned scope does nothing until it is entered with `async with`; entering it is what records the work item."""
        return WorkItemScope(self._run_context, work_item)

    def _run_status(self, exc: BaseException | None) -> StepStatus:
        run_failed: bool = exc is not None or self._run_context.run_recorder.failed_work_item_count() > 0
        return StepStatus.FAILED if run_failed else StepStatus.COMPLETE

    def _log_run_finished(self, elapsed_seconds: float, run_status: StepStatus) -> None:
        failed_count: int = self._run_context.run_recorder.failed_work_item_count()
        total_count: int = self._run_context.run_recorder.work_item_count()
        summary: str = f"{total_count} work item(s): {total_count - failed_count} complete, {failed_count} failed"
        attributes: AttributeBag = self._boundary_attributes(run_status)
        attributes[AttributeKey.ELAPSED_SECONDS] = round(elapsed_seconds, _ELAPSED_SECONDS_DECIMALS)
        attributes[AttributeKey.OUTCOME] = summary
        level: int = logging.WARNING if run_status is StepStatus.FAILED else logging.INFO
        self._run_context.log(
            level,
            f"Run {self._run_id} of {self._pipeline_name} {run_status.value.lower()} in {format_elapsed(elapsed_seconds)}: {summary}",
            attributes,
        )

    def _boundary_attributes(self, run_status: StepStatus) -> AttributeBag:
        return {
            AttributeKey.EVENT: EventKind.RUN,
            AttributeKey.STATUS: run_status.value,
        }

    async def _emit_manifest(self, elapsed_seconds: float, run_status: StepStatus, *, original_error: BaseException | None) -> None:
        run_artifact: RunArtifact = self._build_manifest_artifact(elapsed_seconds, run_status)
        try:
            await self._run_context.persist(run_artifact)
        except ArtifactSinkException as artifact_sink_exception:
            if original_error is None:
                raise
            self._report_lost_manifest(run_artifact, original_error, artifact_sink_exception)
            return
        self._log_run_artifact_emitted(run_artifact)

    def _build_manifest_artifact(self, elapsed_seconds: float, run_status: StepStatus) -> RunArtifact:
        content: bytes = self._run_context.run_recorder.serialize_manifest(
            started_at=self._started_at,
            finished_at=self._run_context.clock.now(),
            elapsed_seconds=elapsed_seconds,
            run_status=run_status,
        )
        return RunArtifact(artifact_kind=MANIFEST_KIND, content=content)

    def _log_run_artifact_emitted(self, run_artifact: RunArtifact) -> None:
        byte_count: int = len(run_artifact.content)
        attributes: AttributeBag = {
            AttributeKey.ARTIFACT_KIND: run_artifact.artifact_type,
            AttributeKey.ARTIFACT_FILENAME: run_artifact.filename,
            AttributeKey.ARTIFACT_BYTES: byte_count,
        }
        self._run_context.log(logging.INFO, f"Emitted artifact: {run_artifact.filename} ({format_byte_size(byte_count)})", attributes)

    def _report_lost_manifest(self, run_artifact: RunArtifact, original_error: BaseException, artifact_sink_exception: ArtifactSinkException) -> None:
        # The run is already failing; losing the manifest must not hide why. The run's own failure stays the one that escapes,
        # carrying the lost manifest and the sink's underlying failure as a note, so the host reports both, once, at its boundary.
        # The sink's failure is logged here with its traceback, because nothing else will raise it.
        lost_manifest_description: str = f"The run manifest could not be persisted either: {_describe_sink_failure(artifact_sink_exception)}"
        original_error.add_note(lost_manifest_description)
        sink_failure: BaseException = artifact_sink_exception.__cause__ or artifact_sink_exception
        attributes: AttributeBag = {
            AttributeKey.ARTIFACT_KIND: run_artifact.artifact_type,
            AttributeKey.ARTIFACT_FILENAME: run_artifact.filename,
            AttributeKey.FAILURE_TYPE: type(sink_failure).__name__,
            AttributeKey.FAILURE_MESSAGE: str(sink_failure),
        }
        self._run_context.log(logging.ERROR, lost_manifest_description, attributes, exception=artifact_sink_exception)


def _require_run_artifact_kind(artifact_kind: ArtifactKind) -> None:
    if artifact_kind.key == MANIFEST_KIND.key:
        raise InvalidDeclarationException(f"The artifact kind '{MANIFEST_KIND.key}' is reserved for the manifest the run writes when it closes")


def _require_pipeline_name(pipeline_name: str) -> None:
    if not pipeline_name.strip():
        raise InvalidDeclarationException("A pipeline run needs a name, such as 'invoice-field-extraction'")


def _validate_caller_attributes(attributes: Mapping[str, AttributeValue] | None) -> AttributeBag:
    caller_attributes: AttributeBag = dict(attributes or {})
    reserved_names: frozenset[str] = _RESERVED_RECORD_ATTRIBUTES.intersection(caller_attributes)
    if reserved_names:
        raise InvalidDeclarationException(f"Run attributes may not use reserved logging attribute names: {sorted(reserved_names)}")
    return caller_attributes


def _create_run_id(run_clock: Clock) -> str:
    return f"{run_clock.now():%Y%m%d_%H%M%S}_{uuid4().hex[:8]}"


def _describe_sink_failure(artifact_sink_exception: ArtifactSinkException) -> str:
    """The sink's own message, followed by the failure underneath it, which is what explains the outage."""
    sink_failure: BaseException | None = artifact_sink_exception.__cause__
    if sink_failure is None:
        return str(artifact_sink_exception)
    return f"{artifact_sink_exception} because of {type(sink_failure).__name__}: {sink_failure}"
