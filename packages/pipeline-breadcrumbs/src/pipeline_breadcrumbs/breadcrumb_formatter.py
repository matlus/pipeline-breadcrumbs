"""The human rendering of breadcrumb records.

One record carries one clean line plus named attributes. This formatter is the only place
that turns them into banners, details and (optionally) times. A host with a different
handler, such as OpenTelemetry or a JSON-lines writer, ignores this class and still gets
the message, the attributes and the record's own timestamp.
"""

import logging
from datetime import UTC, datetime
from enum import StrEnum
from typing import Final, final, override

from pipeline_breadcrumbs.attributes import AttributeKey, EventKind
from pipeline_breadcrumbs.formatting import format_elapsed
from pipeline_breadcrumbs.steps import StepStatus

_DEFAULT_BANNER_WIDTH: Final[int] = 80


class TimeDisplay(StrEnum):
    """Where a time of day appears in the human log. A logging-end decision, never the pipeline's."""

    NONE = "none"
    BOUNDARIES = "boundaries"
    ALL = "all"


@final
class BreadcrumbFormatter(logging.Formatter):
    """Draws boundary records as banners and everything else as plain lines.

    ```
    ================================================================================
    STEP 2.3: Metadata Audit - COMPLETE (14:03:25)
    Found 5 write-up starts in 3.214s
    ================================================================================
    ```

    `time_display` is the single switch for time. By default the time of day appears in
    the banner header only; progress lines between boundaries carry nothing extra.
    """

    def __init__(self, *, time_display: TimeDisplay = TimeDisplay.BOUNDARIES, banner_width: int = _DEFAULT_BANNER_WIDTH) -> None:
        super().__init__()
        self._time_display: TimeDisplay = time_display
        self._separator: str = "=" * banner_width

    @override
    def format(self, record: logging.LogRecord) -> str:
        # `record` is the parameter name `logging.Formatter.format` declares; an override must keep it.
        event: object = record.__dict__.get(AttributeKey.EVENT)
        if isinstance(event, str):
            return self._format_boundary(record, event)
        return self._format_progress(record)

    def _format_progress(self, log_record: logging.LogRecord) -> str:
        text: str = f"{log_record.getMessage()}{self._details_suffix(log_record)}"
        if self._time_display is TimeDisplay.ALL:
            text = f"{self._time_of_day(log_record)}  {text}"
        if log_record.exc_info:
            text = f"{text}\n{self.formatException(log_record.exc_info)}"
        return text

    def _format_boundary(self, log_record: logging.LogRecord, event: str) -> str:
        boundary_status: str = self._text(log_record, AttributeKey.STATUS) or ""
        title: str = f"{self._title(log_record, event)} - {boundary_status}"
        if self._time_display is not TimeDisplay.NONE:
            title = f"{title} ({self._time_of_day(log_record)})"
        lines: list[str] = [self._separator, title]
        summary: str | None = self._summary(log_record, boundary_status)
        if summary:
            lines.append(f"{summary}{self._details_suffix(log_record)}")
        lines.append(self._separator)
        # One leading blank line sets the banner apart; two banners in a row never leave a double gap.
        return "\n" + "\n".join(lines)

    def _title(self, log_record: logging.LogRecord, event: str) -> str:
        if event == EventKind.STEP:
            return f"STEP {self._text(log_record, AttributeKey.STEP_NUMBER)}: {self._text(log_record, AttributeKey.STEP_NAME)}"
        if event == EventKind.WORK_ITEM:
            return f"WORK ITEM: {self._text(log_record, AttributeKey.WORK_ITEM_NAME)}"
        return f"RUN: {self._text(log_record, AttributeKey.PIPELINE_NAME)}"

    def _summary(self, log_record: logging.LogRecord, boundary_status: str) -> str | None:
        elapsed: float | None = self._number(log_record, AttributeKey.ELAPSED_SECONDS)
        outcome: str | None = self._text(log_record, AttributeKey.OUTCOME)
        if boundary_status == StepStatus.COMPLETE.value and elapsed is not None:
            return f"{outcome} in {format_elapsed(elapsed)}" if outcome else f"Completed in {format_elapsed(elapsed)}"
        if boundary_status == StepStatus.FAILED.value and elapsed is not None:
            failure_type: str | None = self._text(log_record, AttributeKey.FAILURE_TYPE)
            if failure_type is None and outcome:
                # A run fails because a work item failed, with no exception of its own: its outcome says how.
                return f"Failed after {format_elapsed(elapsed)}: {outcome}"
            failure_message: str = self._text(log_record, AttributeKey.FAILURE_MESSAGE) or ""
            return f"Failed after {format_elapsed(elapsed)}: {failure_type or 'Error'}: {failure_message}".rstrip(": ")
        if boundary_status == StepStatus.SKIPPED.value and outcome:
            return f"Skipped: {outcome}"
        return None

    @staticmethod
    def _details_suffix(log_record: logging.LogRecord) -> str:
        prefix: str = AttributeKey.DETAIL_PREFIX
        detail_texts: list[str] = []
        key: str
        value: object
        for key, value in log_record.__dict__.items():
            if key.startswith(prefix):
                detail_texts.append(f"{key[len(prefix) :]}={value}")
        return f" ({', '.join(detail_texts)})" if detail_texts else ""

    @staticmethod
    def _text(log_record: logging.LogRecord, key: str) -> str | None:
        value: object = log_record.__dict__.get(key)
        return str(value) if value is not None else None

    @staticmethod
    def _number(log_record: logging.LogRecord, key: str) -> float | None:
        value: object = log_record.__dict__.get(key)
        return float(value) if isinstance(value, int | float) else None

    @staticmethod
    def _time_of_day(log_record: logging.LogRecord) -> str:
        return datetime.fromtimestamp(log_record.created, tz=UTC).astimezone().strftime("%H:%M:%S")
