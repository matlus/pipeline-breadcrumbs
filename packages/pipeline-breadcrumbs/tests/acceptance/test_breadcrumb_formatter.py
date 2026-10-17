# Acceptance tests for the human rendering of the trail: banners at boundaries, plain lines between
# them, and a single switch for where the time of day appears. The records come from a real run;
# the observation is the text the formatter produces for them.

import contextlib
import logging
import re
from collections.abc import Iterable
from typing import Final

import pytest
from breadcrumbs_acceptance_support.asserters.asserter_rendered_text import AsserterRenderedText, ExpectedRenderedText
from breadcrumbs_acceptance_support.clock_testing import ClockTesting
from breadcrumbs_acceptance_support.data_generators import create_random_pipeline_name, create_random_work_item
from breadcrumbs_acceptance_support.exceptions_testing import PlainTestingError

from pipeline_breadcrumbs import BreadcrumbFormatter, PipelineRun, Step, TimeDisplay, WorkItem
from pipeline_breadcrumbs.testing import ArtifactSinkTesting, RecordCapture

METADATA_AUDIT: Final[Step] = Step(2, "Metadata Audit")
STEP_SECONDS: Final[float] = 2.5
PROGRESS_MESSAGE: Final[str] = "Auditing metadata"
OUTCOME: Final[str] = "Found 5 write-up starts"
FAILURE_MESSAGE: Final[str] = "response was not json"
DEFAULT_BANNER_WIDTH: Final[int] = 80
BANNER_SEPARATOR_CHARACTER: Final[str] = "="
TIME_OF_DAY_IN_HEADER: Final[re.Pattern[str]] = re.compile(r"\(\d\d:\d\d:\d\d\)")
TIME_OF_DAY_AT_LINE_START: Final[re.Pattern[str]] = re.compile(r"^\d\d:\d\d:\d\d {2}")


async def _run_one_step(clock_testing: ClockTesting, run_logger: logging.Logger, pipeline_name: str, *, fails: bool = False) -> None:
    work_item: WorkItem = create_random_work_item()
    pipeline_run: PipelineRun = PipelineRun(
        pipeline_name=pipeline_name, artifact_sink=ArtifactSinkTesting(), logger=run_logger, supplied_clock=clock_testing.clock
    )
    # A host handles a work item's failure inside the run, so the run itself always closes without an exception.
    async with pipeline_run:
        with contextlib.suppress(PlainTestingError):
            async with pipeline_run.open_work_item(work_item) as work_item_scope, work_item_scope.step(METADATA_AUDIT) as step_scope:
                step_scope.info(PROGRESS_MESSAGE, pages=14)
                clock_testing.advance(STEP_SECONDS)
                step_scope.outcome(OUTCOME)
                if fails:
                    raise PlainTestingError(FAILURE_MESSAGE)


def _retrieve_text(actual_texts: Iterable[str], marker: str) -> str:
    return next(actual_text for actual_text in actual_texts if marker in actual_text)


@pytest.mark.acceptance
class TestBanners:
    async def test_BreadcrumbFormatter_WhenAStepBoundaryIsRendered_ThenItIsABannerWithTheTimeInItsHeader(
        self, clock_testing: ClockTesting, run_logger: logging.Logger, record_capture: RecordCapture
    ) -> None:
        # Arrange
        await _run_one_step(clock_testing, run_logger, create_random_pipeline_name())
        breadcrumb_formatter: BreadcrumbFormatter = BreadcrumbFormatter()
        expected_started_banner_rendered_text: ExpectedRenderedText = ExpectedRenderedText(
            starts_with="\n" + BANNER_SEPARATOR_CHARACTER * DEFAULT_BANNER_WIDTH + "\n", present_patterns=[TIME_OF_DAY_IN_HEADER]
        )
        expected_complete_banner_rendered_text: ExpectedRenderedText = ExpectedRenderedText(contained_phrases=[f"{OUTCOME} in 2.500s"])

        # Act
        actual_texts: list[str] = [breadcrumb_formatter.format(actual_log_record) for actual_log_record in record_capture.records]

        # Assert
        AsserterRenderedText.assert_text(expected_started_banner_rendered_text, _retrieve_text(actual_texts, "STEP 2: Metadata Audit - STARTED"))
        AsserterRenderedText.assert_text(expected_complete_banner_rendered_text, _retrieve_text(actual_texts, "STEP 2: Metadata Audit - COMPLETE"))

    async def test_BreadcrumbFormatter_WhenAStepFailed_ThenTheBannerNamesTheFailure(
        self, clock_testing: ClockTesting, run_logger: logging.Logger, record_capture: RecordCapture
    ) -> None:
        # Arrange
        await _run_one_step(clock_testing, run_logger, create_random_pipeline_name(), fails=True)
        breadcrumb_formatter: BreadcrumbFormatter = BreadcrumbFormatter()
        expected_failed_banner_rendered_text: ExpectedRenderedText = ExpectedRenderedText(
            contained_phrases=[f"Failed after 2.500s: PlainTestingError: {FAILURE_MESSAGE}"]
        )

        # Act
        actual_texts: list[str] = [breadcrumb_formatter.format(actual_log_record) for actual_log_record in record_capture.records]

        # Assert
        AsserterRenderedText.assert_text(expected_failed_banner_rendered_text, _retrieve_text(actual_texts, "STEP 2: Metadata Audit - FAILED"))

    async def test_BreadcrumbFormatter_WhenARunFailedBecauseAWorkItemFailed_ThenTheBannerShowsTheWorkItemCounts(
        self, clock_testing: ClockTesting, run_logger: logging.Logger, record_capture: RecordCapture
    ) -> None:
        # Arrange - the work item's exception is handled inside the run, so the run itself has no exception to name
        pipeline_name: str = create_random_pipeline_name()
        await _run_one_step(clock_testing, run_logger, pipeline_name, fails=True)
        breadcrumb_formatter: BreadcrumbFormatter = BreadcrumbFormatter()
        expected_run_banner_rendered_text: ExpectedRenderedText = ExpectedRenderedText(
            contained_phrases=["Failed after 2.500s: 1 work item(s): 0 complete, 1 failed"], absent_phrases=["Error"]
        )

        # Act
        actual_texts: list[str] = [breadcrumb_formatter.format(actual_log_record) for actual_log_record in record_capture.records]

        # Assert
        AsserterRenderedText.assert_text(expected_run_banner_rendered_text, _retrieve_text(actual_texts, f"RUN: {pipeline_name} - FAILED"))

    async def test_BreadcrumbFormatter_WhenTheBannerWidthIsConfigured_ThenTheSeparatorUsesIt(
        self, clock_testing: ClockTesting, run_logger: logging.Logger, record_capture: RecordCapture
    ) -> None:
        # Arrange
        await _run_one_step(clock_testing, run_logger, create_random_pipeline_name())
        banner_width: int = 40
        breadcrumb_formatter: BreadcrumbFormatter = BreadcrumbFormatter(banner_width=banner_width)
        expected_first_banner_rendered_text: ExpectedRenderedText = ExpectedRenderedText(
            contained_phrases=[BANNER_SEPARATOR_CHARACTER * banner_width], absent_phrases=[BANNER_SEPARATOR_CHARACTER * (banner_width + 1)]
        )

        # Act
        actual_first_banner: str = breadcrumb_formatter.format(record_capture.records[0])

        # Assert
        AsserterRenderedText.assert_text(expected_first_banner_rendered_text, actual_first_banner)


@pytest.mark.acceptance
class TestTimeDisplay:
    async def test_BreadcrumbFormatter_WhenTheDefaultIsUsed_ThenProgressLinesCarryNoTime(
        self, clock_testing: ClockTesting, run_logger: logging.Logger, record_capture: RecordCapture
    ) -> None:
        # Arrange
        await _run_one_step(clock_testing, run_logger, create_random_pipeline_name())
        breadcrumb_formatter: BreadcrumbFormatter = BreadcrumbFormatter()
        expected_progress_line: str = f"{PROGRESS_MESSAGE} (pages=14)"

        # Act
        actual_texts: list[str] = [breadcrumb_formatter.format(actual_log_record) for actual_log_record in record_capture.records]

        # Assert
        actual_progress_line: str = next(actual_text for actual_text in actual_texts if actual_text.startswith(PROGRESS_MESSAGE))
        assert actual_progress_line == expected_progress_line

    async def test_BreadcrumbFormatter_WhenTimeDisplayIsNone_ThenNoLineCarriesATime(
        self, clock_testing: ClockTesting, run_logger: logging.Logger, record_capture: RecordCapture
    ) -> None:
        # Arrange
        await _run_one_step(clock_testing, run_logger, create_random_pipeline_name())
        breadcrumb_formatter: BreadcrumbFormatter = BreadcrumbFormatter(time_display=TimeDisplay.NONE)
        expected_every_rendered_text: ExpectedRenderedText = ExpectedRenderedText(absent_patterns=[TIME_OF_DAY_IN_HEADER, TIME_OF_DAY_AT_LINE_START])

        # Act
        actual_texts: list[str] = [breadcrumb_formatter.format(actual_log_record) for actual_log_record in record_capture.records]

        # Assert
        AsserterRenderedText.assert_every_text(expected_every_rendered_text, actual_texts)

    async def test_BreadcrumbFormatter_WhenTimeDisplayIsAll_ThenEveryProgressLineStartsWithATime(
        self, clock_testing: ClockTesting, run_logger: logging.Logger, record_capture: RecordCapture
    ) -> None:
        # Arrange
        await _run_one_step(clock_testing, run_logger, create_random_pipeline_name())
        breadcrumb_formatter: BreadcrumbFormatter = BreadcrumbFormatter(time_display=TimeDisplay.ALL)
        expected_progress_line_rendered_text: ExpectedRenderedText = ExpectedRenderedText(present_patterns=[TIME_OF_DAY_AT_LINE_START])

        # Act
        actual_texts: list[str] = [breadcrumb_formatter.format(actual_log_record) for actual_log_record in record_capture.records]

        # Assert
        AsserterRenderedText.assert_text(expected_progress_line_rendered_text, _retrieve_text(actual_texts, PROGRESS_MESSAGE))

    @pytest.mark.parametrize("time_display", list(TimeDisplay))
    async def test_BreadcrumbFormatter_WhenAnyTimeDisplayIsChosen_ThenTheRecordsOwnMessageStaysOneCleanLine(
        self, time_display: TimeDisplay, clock_testing: ClockTesting, run_logger: logging.Logger, record_capture: RecordCapture
    ) -> None:
        # Arrange - presentation never leaks into the record, so a different handler still gets a clean message
        await _run_one_step(clock_testing, run_logger, create_random_pipeline_name())
        breadcrumb_formatter: BreadcrumbFormatter = BreadcrumbFormatter(time_display=time_display)
        expected_every_message_rendered_text: ExpectedRenderedText = ExpectedRenderedText(absent_phrases=["\n", BANNER_SEPARATOR_CHARACTER * 10])

        # Act
        for actual_log_record in record_capture.records:
            breadcrumb_formatter.format(actual_log_record)

        # Assert
        AsserterRenderedText.assert_every_text(
            expected_every_message_rendered_text, [actual_log_record.getMessage() for actual_log_record in record_capture.records]
        )


@pytest.mark.acceptance
class TestPlainRecords:
    def test_BreadcrumbFormatter_WhenARecordHasNoBreadcrumbAttributes_ThenItRendersAsItsMessage(self) -> None:
        # Arrange
        expected_text: str = "plain message"
        plain_log_record: logging.LogRecord = logging.LogRecord("x", logging.INFO, "f.py", 1, expected_text, (), None)

        # Act
        actual_text: str = BreadcrumbFormatter().format(plain_log_record)

        # Assert
        assert actual_text == expected_text

    def test_BreadcrumbFormatter_WhenARecordCarriesAnException_ThenTheTracebackIsAppended(self) -> None:
        # Arrange
        exception_message: str = "boom"
        log_record_message: str = "failed"
        plain_testing_error: PlainTestingError = PlainTestingError(exception_message)
        failed_log_record: logging.LogRecord = logging.LogRecord(
            "x", logging.ERROR, "f.py", 1, log_record_message, (), (type(plain_testing_error), plain_testing_error, None)
        )
        expected_rendered_text: ExpectedRenderedText = ExpectedRenderedText(
            starts_with=f"{log_record_message}\n", ends_with=f"PlainTestingError: {exception_message}"
        )

        # Act
        actual_text: str = BreadcrumbFormatter().format(failed_log_record)

        # Assert
        AsserterRenderedText.assert_text(expected_rendered_text, actual_text)
