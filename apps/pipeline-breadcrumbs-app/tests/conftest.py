import logging
from collections.abc import Iterator

import pytest

from pipeline_breadcrumbs.testing import ArtifactRecorder, RecordCapture

_TEST_LOGGER_NAME: str = "pipeline_breadcrumbs_app.acceptance_tests"


@pytest.fixture
def artifact_recorder() -> ArtifactRecorder:
    return ArtifactRecorder()


@pytest.fixture
def record_capture() -> Iterator[RecordCapture]:
    """Captures every record the system logs, and leaves the shared logger exactly as it found it."""
    record_capture: RecordCapture = RecordCapture()
    test_logger: logging.Logger = logging.getLogger(_TEST_LOGGER_NAME)
    previous_level: int = test_logger.level
    previous_propagate: bool = test_logger.propagate
    test_logger.setLevel(logging.DEBUG)
    test_logger.propagate = False
    test_logger.addHandler(record_capture)
    try:
        yield record_capture
    finally:
        test_logger.removeHandler(record_capture)
        test_logger.setLevel(previous_level)
        test_logger.propagate = previous_propagate


@pytest.fixture
def run_logger(record_capture: RecordCapture) -> logging.Logger:
    """The logger a run is given; `record_capture` is attached to it."""
    return logging.getLogger(_TEST_LOGGER_NAME)
