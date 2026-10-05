"""One execution of a pipeline, from its first work item to its manifest."""

import logging
from collections.abc import Mapping
from datetime import datetime
from types import TracebackType
from typing import Final, Self, final
from uuid import uuid4

from pipeline_breadcrumbs.artifacts import ArtifactSink, RunArtifact
from pipeline_breadcrumbs.attributes import AttributeBag, AttributeKey, AttributeValue, EventKind
from pipeline_breadcrumbs.clock import Clock
from pipeline_breadcrumbs.errors import ArtifactSinkError
from pipeline_breadcrumbs.formatting import format_byte_size, format_elapsed
from pipeline_breadcrumbs.manifest import MANIFEST_KIND, RunRecorder
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
        name: str,
        sink: ArtifactSink,
        logger: logging.Logger | None = None,
        attributes: Mapping[str, AttributeValue] | None = None,
        clock: Clock | None = None,
    ) -> None:
        if not name.strip():
            raise ValueError("A pipeline run needs a name, such as 'invoice-field-extraction'")
        resolved_clock: Clock = clock or Clock.system()
        caller_attributes: AttributeBag = dict(attributes or {})
        reserved_names: frozenset[str] = _RESERVED_RECORD_ATTRIBUTES.intersection(caller_attributes)
        if reserved_names:
            raise ValueError(f"Run attributes may not use reserved logging attribute names: {sorted(reserved_names)}")
        self._run_id: str = f"{resolved_clock.now():%Y%m%d_%H%M%S}_{uuid4().hex[:8]}"
        self._name: str = name
        self._run_context: RunContext = RunContext(
            sink=sink,
            logger=logger or logging.getLogger(DEFAULT_LOGGER_NAME),
            base_attributes={
                **caller_attributes,
                AttributeKey.PIPELINE_NAME: name,
                AttributeKey.RUN_ID: self._run_id,
            },
            clock=resolved_clock,
            run_recorder=RunRecorder(pipeline_name=name, run_id=self._run_id),
        )
        self._started: float = 0.0
        self._started_at: datetime = resolved_clock.now()

    @property
    def run_id(self) -> str:
        return self._run_id

    async def __aenter__(self) -> Self:
        self._started = self._run_context.clock.monotonic()
        self._started_at = self._run_context.clock.now()
        self._run_context.log(
            logging.INFO,
            f"Run {self._run_id} of {self._name} started",
            self._boundary_attributes(StepStatus.STARTED),
        )
        return self

    async def __aexit__(self, _exc_type: type[BaseException] | None, exc: BaseException | None, _traceback: TracebackType | None) -> None:
        elapsed_seconds: float = self._run_context.clock.monotonic() - self._started
        run_status: StepStatus = self._run_status(exc)
        self._log_run_finished(elapsed_seconds, run_status)
        await self._emit_manifest(elapsed_seconds, run_status, original_error=exc)

    def work_item(self, work_item: WorkItem) -> WorkItemScope:
        """Open a work item on this run."""
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
            f"Run {self._run_id} of {self._name} {run_status.value.lower()} in {format_elapsed(elapsed_seconds)}: {summary}",
            attributes,
        )

    def _boundary_attributes(self, run_status: StepStatus) -> AttributeBag:
        return {
            AttributeKey.EVENT: EventKind.RUN,
            AttributeKey.STATUS: run_status.value,
        }

    async def _emit_manifest(self, elapsed_seconds: float, run_status: StepStatus, *, original_error: BaseException | None) -> None:
        content: bytes = self._run_context.run_recorder.serialize(
            started_at=self._started_at,
            finished_at=self._run_context.clock.now(),
            elapsed_seconds=elapsed_seconds,
            run_status=run_status,
        )
        run_artifact: RunArtifact = RunArtifact(artifact_kind=MANIFEST_KIND, content=content)
        try:
            await self._run_context.persist(run_artifact)
        except ArtifactSinkError:
            if original_error is None:
                raise
            # The run is already failing; losing the manifest must not hide why.
            self._run_context.log(logging.WARNING, f"Could not persist {run_artifact.filename} while the run was failing", {})
            return
        attributes: AttributeBag = {
            AttributeKey.ARTIFACT_KIND: run_artifact.artifact_type,
            AttributeKey.ARTIFACT_FILENAME: run_artifact.filename,
            AttributeKey.ARTIFACT_BYTES: len(content),
        }
        self._run_context.log(logging.INFO, f"Emitted artifact: {run_artifact.filename} ({format_byte_size(len(content))})", attributes)
