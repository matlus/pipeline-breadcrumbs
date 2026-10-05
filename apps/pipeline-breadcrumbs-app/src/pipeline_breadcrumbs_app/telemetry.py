"""A stand-in for Application Insights: a log handler that receives exceptions and nothing else.

A hosted application keeps its informational lines (step 1 started, step 1 complete, timings) in the
platform's own process logs, and sends only exceptions to telemetry. This handler plays the telemetry
side for the demo by writing one JSON line per exception. A real host attaches the Azure Monitor
OpenTelemetry handler at the same level instead; the system never knows which handlers exist.
"""

import json
import logging
from collections.abc import Generator
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from types import TracebackType
from typing import Final, final, override

from pipeline_breadcrumbs import ContextualDataDict, ContextualExceptionProtocol

TELEMETRY_FILENAME: Final[str] = "telemetry.jsonl"

# Every attribute the library puts on a record starts with this, so telemetry can carry them as custom dimensions.
_PIPELINE_ATTRIBUTE_PREFIX: Final[str] = "pipeline."


@final
@dataclass(frozen=True, slots=True)
class ExceptionTelemetry:
    """One exception as telemetry receives it: what failed, where, and every named fact it carries."""

    timestamp: str
    severity: str
    message: str
    exception_type: str | None
    stack_trace: str | None
    custom_dimensions: ContextualDataDict


@final
class ExceptionTelemetryHandler(logging.Handler):
    """Writes one JSON line per record at error level or above. Informational and warning records never reach it."""

    def __init__(self, telemetry_path: Path) -> None:
        super().__init__(level=logging.ERROR)
        self._telemetry_path: Path = telemetry_path

    @override
    def emit(self, record: logging.LogRecord) -> None:
        try:
            exception_telemetry: ExceptionTelemetry = self._to_telemetry(record)
            with self._telemetry_path.open("a", encoding="utf-8") as telemetry_file:
                telemetry_file.write(json.dumps(asdict(exception_telemetry)) + "\n")
        except Exception:  # noqa: BLE001 - logging must never raise into the code that logged
            self.handleError(record)

    @staticmethod
    def _to_telemetry(record: logging.LogRecord) -> ExceptionTelemetry:
        exception: BaseException | None = record.exc_info[1] if record.exc_info else None
        traceback_of_exception: TracebackType | None = record.exc_info[2] if record.exc_info else None
        custom_dimensions: ContextualDataDict = {}
        for attribute_name, attribute_value in record.__dict__.items():
            if attribute_name.startswith(_PIPELINE_ATTRIBUTE_PREFIX) and isinstance(attribute_value, str | int | float | bool):
                custom_dimensions[attribute_name] = attribute_value
        if isinstance(exception, ContextualExceptionProtocol):
            custom_dimensions.update(exception.contextual_data_by_name)
        return ExceptionTelemetry(
            timestamp=datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
            severity=record.levelname,
            message=record.getMessage(),
            exception_type=type(exception).__name__ if exception is not None else None,
            stack_trace="".join(logging.Formatter().formatException((type(exception), exception, traceback_of_exception)))
            if exception is not None
            else None,
            custom_dimensions=custom_dimensions,
        )


@contextmanager
def attached_exception_telemetry(logger: logging.Logger, telemetry_path: Path) -> Generator[ExceptionTelemetryHandler]:
    """Send the logger's exceptions to `telemetry_path` for the duration of the block, then detach."""
    exception_telemetry_handler: ExceptionTelemetryHandler = ExceptionTelemetryHandler(telemetry_path)
    logger.addHandler(exception_telemetry_handler)
    try:
        yield exception_telemetry_handler
    finally:
        logger.removeHandler(exception_telemetry_handler)
        exception_telemetry_handler.close()
