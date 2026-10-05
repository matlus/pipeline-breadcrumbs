# Acceptance tests for the human rendering of the trail: banners at boundaries, plain lines between
# them, and a single switch for where the time of day appears. The records come from a real run;
# the observation is the text the formatter produces for them.

import contextlib
import logging
import re
from typing import Final

import pytest
from breadcrumbs_acceptance_support.clock_testing import ClockTesting
from breadcrumbs_acceptance_support.data_generators import create_random_work_item

from pipeline_breadcrumbs import BreadcrumbFormatter, PipelineRun, Step, TimeDisplay, WorkItem
from pipeline_breadcrumbs.testing import ArtifactRecorder, RecordCapture

METADATA_AUDIT: Final[Step] = Step(2, "Metadata Audit")
TIME_OF_DAY_IN_HEADER: Final[re.Pattern[str]] = re.compile(r"\(\d\d:\d\d:\d\d\)")
TIME_OF_DAY_AT_LINE_START: Final[re.Pattern[str]] = re.compile(r"^\d\d:\d\d:\d\d {2}")


async def _run_one_step(clock_testing: ClockTesting, run_logger: logging.Logger, *, fails: bool = False) -> None:
    work_item: WorkItem = create_random_work_item()
    pipeline_run: PipelineRun = PipelineRun(name="demo", sink=ArtifactRecorder(), logger=run_logger, clock=clock_testing.clock)
    with contextlib.suppress(ValueError):
        async with pipeline_run, pipeline_run.work_item(work_item) as work_item_scope, work_item_scope.step(METADATA_AUDIT) as step_scope:
            step_scope.info("Auditing metadata", pages=14)
            clock_testing.advance(2.5)
            step_scope.outcome("Found 5 write-up starts")
            if fails:
                raise ValueError("response was not json")


def _render_all(record_capture: RecordCapture, breadcrumb_formatter: BreadcrumbFormatter) -> list[str]:
    return [breadcrumb_formatter.format(actual_log_record) for actual_log_record in record_capture.records]


@pytest.mark.acceptance
class TestBanners:
    async def test_BreadcrumbFormatter_WhenAStepBoundaryIsRendered_ThenItIsABannerWithTheTimeInItsHeader(
        self, clock_testing: ClockTesting, run_logger: logging.Logger, record_capture: RecordCapture
    ) -> None:
        # Arrange
        await _run_one_step(clock_testing, run_logger)

        # Act
        actual_texts: list[str] = _render_all(record_capture, BreadcrumbFormatter())

        # Assert
        actual_started_banner: str = next(actual_text for actual_text in actual_texts if "STEP 2: Metadata Audit - STARTED" in actual_text)
        assert actual_started_banner.startswith("\n" + "=" * 80 + "\n")
        assert TIME_OF_DAY_IN_HEADER.search(actual_started_banner)
        actual_complete_banner: str = next(actual_text for actual_text in actual_texts if "STEP 2: Metadata Audit - COMPLETE" in actual_text)
        assert "Found 5 write-up starts in 2.500s" in actual_complete_banner

    async def test_BreadcrumbFormatter_WhenAStepFailed_ThenTheBannerNamesTheFailure(
        self, clock_testing: ClockTesting, run_logger: logging.Logger, record_capture: RecordCapture
    ) -> None:
        # Arrange
        await _run_one_step(clock_testing, run_logger, fails=True)

        # Act
        actual_texts: list[str] = _render_all(record_capture, BreadcrumbFormatter())

        # Assert
        actual_failed_banner: str = next(actual_text for actual_text in actual_texts if "STEP 2: Metadata Audit - FAILED" in actual_text)
        assert "Failed after 2.500s: ValueError: response was not json" in actual_failed_banner

    async def test_BreadcrumbFormatter_WhenARunFailedBecauseAWorkItemFailed_ThenTheBannerShowsTheWorkItemCounts(
        self, clock_testing: ClockTesting, run_logger: logging.Logger, record_capture: RecordCapture
    ) -> None:
        # Arrange - the work item's exception is handled per item, so the run itself has no exception to name
        await _run_one_step(clock_testing, run_logger, fails=True)

        # Act
        actual_texts: list[str] = _render_all(record_capture, BreadcrumbFormatter())

        # Assert
        actual_run_banner: str = next(actual_text for actual_text in actual_texts if "RUN: demo - FAILED" in actual_text)
        assert "Failed after 2.500s: 1 work item(s): 0 complete, 1 failed" in actual_run_banner
        assert "Error" not in actual_run_banner

    async def test_BreadcrumbFormatter_WhenTheBannerWidthIsConfigured_ThenTheSeparatorUsesIt(
        self, clock_testing: ClockTesting, run_logger: logging.Logger, record_capture: RecordCapture
    ) -> None:
        # Arrange
        await _run_one_step(clock_testing, run_logger)

        # Act
        actual_first_banner: str = _render_all(record_capture, BreadcrumbFormatter(banner_width=40))[0]

        # Assert
        assert "=" * 40 in actual_first_banner
        assert "=" * 41 not in actual_first_banner


@pytest.mark.acceptance
class TestTimeDisplay:
    async def test_BreadcrumbFormatter_WhenTheDefaultIsUsed_ThenProgressLinesCarryNoTime(
        self, clock_testing: ClockTesting, run_logger: logging.Logger, record_capture: RecordCapture
    ) -> None:
        # Arrange
        await _run_one_step(clock_testing, run_logger)

        # Act
        actual_texts: list[str] = _render_all(record_capture, BreadcrumbFormatter())

        # Assert
        actual_progress_line: str = next(actual_text for actual_text in actual_texts if actual_text.startswith("Auditing metadata"))
        expected_progress_line: str = "Auditing metadata (pages=14)"
        assert actual_progress_line == expected_progress_line

    async def test_BreadcrumbFormatter_WhenTimeDisplayIsNone_ThenNoLineCarriesATime(
        self, clock_testing: ClockTesting, run_logger: logging.Logger, record_capture: RecordCapture
    ) -> None:
        # Arrange
        await _run_one_step(clock_testing, run_logger)

        # Act
        actual_texts: list[str] = _render_all(record_capture, BreadcrumbFormatter(time_display=TimeDisplay.NONE))

        # Assert
        for actual_text in actual_texts:
            assert not TIME_OF_DAY_IN_HEADER.search(actual_text)
            assert not TIME_OF_DAY_AT_LINE_START.search(actual_text)

    async def test_BreadcrumbFormatter_WhenTimeDisplayIsAll_ThenEveryProgressLineStartsWithATime(
        self, clock_testing: ClockTesting, run_logger: logging.Logger, record_capture: RecordCapture
    ) -> None:
        # Arrange
        await _run_one_step(clock_testing, run_logger)

        # Act
        actual_texts: list[str] = _render_all(record_capture, BreadcrumbFormatter(time_display=TimeDisplay.ALL))

        # Assert
        actual_progress_line: str = next(actual_text for actual_text in actual_texts if "Auditing metadata" in actual_text)
        assert TIME_OF_DAY_AT_LINE_START.search(actual_progress_line)

    @pytest.mark.parametrize("time_display", list(TimeDisplay))
    async def test_BreadcrumbFormatter_WhenAnyTimeDisplayIsChosen_ThenTheRecordsOwnMessageStaysOneCleanLine(
        self, time_display: TimeDisplay, clock_testing: ClockTesting, run_logger: logging.Logger, record_capture: RecordCapture
    ) -> None:
        # Arrange
        await _run_one_step(clock_testing, run_logger)

        # Act
        _render_all(record_capture, BreadcrumbFormatter(time_display=time_display))

        # Assert - presentation never leaks into the record, so a different handler still gets a clean message
        for actual_log_record in record_capture.records:
            assert "\n" not in actual_log_record.getMessage()
            assert "=" * 10 not in actual_log_record.getMessage()


@pytest.mark.acceptance
class TestPlainRecords:
    def test_BreadcrumbFormatter_WhenARecordHasNoBreadcrumbAttributes_ThenItRendersAsItsMessage(self) -> None:
        # Arrange
        actual_log_record: logging.LogRecord = logging.LogRecord("x", logging.INFO, "f.py", 1, "plain message", (), None)

        # Act
        actual_text: str = BreadcrumbFormatter().format(actual_log_record)

        # Assert
        assert actual_text == "plain message"

    def test_BreadcrumbFormatter_WhenARecordCarriesAnException_ThenTheTracebackIsAppended(self) -> None:
        # Arrange
        raised_error: ValueError = ValueError("boom")
        actual_log_record: logging.LogRecord = logging.LogRecord(
            "x", logging.ERROR, "f.py", 1, "failed", (), (type(raised_error), raised_error, None)
        )

        # Act
        actual_text: str = BreadcrumbFormatter().format(actual_log_record)

        # Assert
        assert actual_text.startswith("failed\n")
        assert actual_text.endswith("ValueError: boom")
