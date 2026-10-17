# Acceptance tests for the human rendering of the trail: banners at boundaries, plain lines between
# them, and a single switch for where the time of day appears. The records come from a real run;
# the observation is the text the formatter produces for them.

import contextlib
import logging
import re
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Final

import pytest
from breadcrumbs_acceptance_support.asserters.asserter_rendered_text import EveryRenderedTextAsserter, ExpectedRenderedText, RenderedTextAsserter
from breadcrumbs_acceptance_support.clock_testing import ClockTesting
from breadcrumbs_acceptance_support.data_generators import (
    create_random_failure_message,
    create_random_log_message,
    create_random_logger_name,
    create_random_outcome,
    create_random_pipeline_name,
    create_random_progress_message,
    create_random_source_path,
    create_random_work_item,
)
from breadcrumbs_acceptance_support.exceptions_testing import PlainTestingError

from pipeline_breadcrumbs import BreadcrumbFormatter, PipelineRun, Step, TimeDisplay, WorkItem
from pipeline_breadcrumbs.testing import ArtifactSinkTesting, RecordCapture

METADATA_AUDIT: Final[Step] = Step(2, "Metadata Audit")
STEP_SECONDS: Final[float] = 2.5
DEFAULT_BANNER_WIDTH: Final[int] = 80
BANNER_SEPARATOR_CHARACTER: Final[str] = "="
TIME_OF_DAY_IN_HEADER: Final[re.Pattern[str]] = re.compile(r"\(\d\d:\d\d:\d\d\)")
TIME_OF_DAY_AT_LINE_START: Final[re.Pattern[str]] = re.compile(r"^\d\d:\d\d:\d\d {2}")


@dataclass(frozen=True)
class OneStepRunScenario:
    """What one run of a single step says along the way, so each test asserts back the words its own run used."""

    pipeline_name: str
    progress_message: str
    outcome: str
    failure_message: str


def create_random_one_step_run_scenario() -> OneStepRunScenario:
    return OneStepRunScenario(
        pipeline_name=create_random_pipeline_name(),
        progress_message=create_random_progress_message(),
        outcome=create_random_outcome(),
        failure_message=create_random_failure_message(),
    )


async def _run_one_step(
    clock_testing: ClockTesting, run_logger: logging.Logger, one_step_run_scenario: OneStepRunScenario, *, fails: bool = False
) -> None:
    work_item: WorkItem = create_random_work_item()
    pipeline_run: PipelineRun = PipelineRun(
        pipeline_name=one_step_run_scenario.pipeline_name,
        artifact_sink=ArtifactSinkTesting(),
        logger=run_logger,
        supplied_clock=clock_testing.clock,
    )
    # A host handles a work item's failure inside the run, so the run itself always closes without an exception.
    async with pipeline_run:
        with contextlib.suppress(PlainTestingError):
            async with pipeline_run.open_work_item(work_item) as work_item_scope, work_item_scope.step(METADATA_AUDIT) as step_scope:
                step_scope.info(one_step_run_scenario.progress_message, pages=14)
                clock_testing.advance(STEP_SECONDS)
                step_scope.outcome(one_step_run_scenario.outcome)
                if fails:
                    raise PlainTestingError(one_step_run_scenario.failure_message)


def _retrieve_text(actual_texts: Iterable[str], marker: str) -> str:
    actual_texts_in_order: list[str] = list(actual_texts)
    actual_text: str | None = next((actual_text for actual_text in actual_texts_in_order if marker in actual_text), None)
    assert actual_text is not None, f"no rendered text contains {marker!r}; the texts were {actual_texts_in_order!r}"
    return actual_text


@pytest.mark.acceptance
class TestBanners:
    async def test_BreadcrumbFormatter_WhenAStepBoundaryIsRendered_ThenItIsABannerWithTheTimeInItsHeader(
        self, clock_testing: ClockTesting, run_logger: logging.Logger, record_capture: RecordCapture
    ) -> None:
        # Arrange
        one_step_run_scenario: OneStepRunScenario = create_random_one_step_run_scenario()
        await _run_one_step(clock_testing, run_logger, one_step_run_scenario)
        breadcrumb_formatter: BreadcrumbFormatter = BreadcrumbFormatter()
        expected_started_banner_rendered_text: ExpectedRenderedText = ExpectedRenderedText(
            starts_with="\n" + BANNER_SEPARATOR_CHARACTER * DEFAULT_BANNER_WIDTH + "\n", present_patterns=[TIME_OF_DAY_IN_HEADER]
        )
        expected_complete_banner_rendered_text: ExpectedRenderedText = ExpectedRenderedText(
            contained_phrases=[f"{one_step_run_scenario.outcome} in 2.500s"]
        )

        # Act
        actual_texts: list[str] = [breadcrumb_formatter.format(actual_log_record) for actual_log_record in record_capture.records]

        # Assert
        RenderedTextAsserter.assert_expected_and_actual_are_equal(
            expected_started_banner_rendered_text, _retrieve_text(actual_texts, "STEP 2: Metadata Audit - STARTED")
        )
        RenderedTextAsserter.assert_expected_and_actual_are_equal(
            expected_complete_banner_rendered_text, _retrieve_text(actual_texts, "STEP 2: Metadata Audit - COMPLETE")
        )

    async def test_BreadcrumbFormatter_WhenAStepFailed_ThenTheBannerNamesTheFailure(
        self, clock_testing: ClockTesting, run_logger: logging.Logger, record_capture: RecordCapture
    ) -> None:
        # Arrange
        one_step_run_scenario: OneStepRunScenario = create_random_one_step_run_scenario()
        await _run_one_step(clock_testing, run_logger, one_step_run_scenario, fails=True)
        breadcrumb_formatter: BreadcrumbFormatter = BreadcrumbFormatter()
        expected_failed_banner_rendered_text: ExpectedRenderedText = ExpectedRenderedText(
            contained_phrases=[f"Failed after 2.500s: PlainTestingError: {one_step_run_scenario.failure_message}"]
        )

        # Act
        actual_texts: list[str] = [breadcrumb_formatter.format(actual_log_record) for actual_log_record in record_capture.records]

        # Assert
        RenderedTextAsserter.assert_expected_and_actual_are_equal(
            expected_failed_banner_rendered_text, _retrieve_text(actual_texts, "STEP 2: Metadata Audit - FAILED")
        )

    async def test_BreadcrumbFormatter_WhenARunFailedBecauseAWorkItemFailed_ThenTheBannerShowsTheWorkItemCounts(
        self, clock_testing: ClockTesting, run_logger: logging.Logger, record_capture: RecordCapture
    ) -> None:
        # Arrange - the work item's exception is handled inside the run, so the run itself has no exception to name
        one_step_run_scenario: OneStepRunScenario = create_random_one_step_run_scenario()
        await _run_one_step(clock_testing, run_logger, one_step_run_scenario, fails=True)
        breadcrumb_formatter: BreadcrumbFormatter = BreadcrumbFormatter()
        expected_run_banner_rendered_text: ExpectedRenderedText = ExpectedRenderedText(
            contained_phrases=["Failed after 2.500s: 1 work item(s): 0 complete, 1 failed"], absent_phrases=["Error"]
        )

        # Act
        actual_texts: list[str] = [breadcrumb_formatter.format(actual_log_record) for actual_log_record in record_capture.records]

        # Assert
        RenderedTextAsserter.assert_expected_and_actual_are_equal(
            expected_run_banner_rendered_text, _retrieve_text(actual_texts, f"RUN: {one_step_run_scenario.pipeline_name} - FAILED")
        )

    async def test_BreadcrumbFormatter_WhenTheBannerWidthIsConfigured_ThenTheSeparatorUsesIt(
        self, clock_testing: ClockTesting, run_logger: logging.Logger, record_capture: RecordCapture
    ) -> None:
        # Arrange
        await _run_one_step(clock_testing, run_logger, create_random_one_step_run_scenario())
        banner_width: int = 40
        breadcrumb_formatter: BreadcrumbFormatter = BreadcrumbFormatter(banner_width=banner_width)
        expected_first_banner_rendered_text: ExpectedRenderedText = ExpectedRenderedText(
            contained_phrases=[BANNER_SEPARATOR_CHARACTER * banner_width], absent_phrases=[BANNER_SEPARATOR_CHARACTER * (banner_width + 1)]
        )

        # Act
        actual_first_banner: str = breadcrumb_formatter.format(record_capture.records[0])

        # Assert
        RenderedTextAsserter.assert_expected_and_actual_are_equal(expected_first_banner_rendered_text, actual_first_banner)


@pytest.mark.acceptance
class TestTimeDisplay:
    async def test_BreadcrumbFormatter_WhenTheDefaultIsUsed_ThenProgressLinesCarryNoTime(
        self, clock_testing: ClockTesting, run_logger: logging.Logger, record_capture: RecordCapture
    ) -> None:
        # Arrange
        one_step_run_scenario: OneStepRunScenario = create_random_one_step_run_scenario()
        await _run_one_step(clock_testing, run_logger, one_step_run_scenario)
        breadcrumb_formatter: BreadcrumbFormatter = BreadcrumbFormatter()
        expected_progress_line: str = f"{one_step_run_scenario.progress_message} (pages=14)"

        # Act
        actual_texts: list[str] = [breadcrumb_formatter.format(actual_log_record) for actual_log_record in record_capture.records]

        # Assert
        assert _retrieve_text(actual_texts, one_step_run_scenario.progress_message) == expected_progress_line

    async def test_BreadcrumbFormatter_WhenTimeDisplayIsNone_ThenNoLineCarriesATime(
        self, clock_testing: ClockTesting, run_logger: logging.Logger, record_capture: RecordCapture
    ) -> None:
        # Arrange
        await _run_one_step(clock_testing, run_logger, create_random_one_step_run_scenario())
        breadcrumb_formatter: BreadcrumbFormatter = BreadcrumbFormatter(time_display=TimeDisplay.NONE)
        expected_every_rendered_text: ExpectedRenderedText = ExpectedRenderedText(absent_patterns=[TIME_OF_DAY_IN_HEADER, TIME_OF_DAY_AT_LINE_START])

        # Act
        actual_texts: list[str] = [breadcrumb_formatter.format(actual_log_record) for actual_log_record in record_capture.records]

        # Assert
        EveryRenderedTextAsserter.assert_expected_and_actual_are_equal(expected_every_rendered_text, actual_texts)

    async def test_BreadcrumbFormatter_WhenTimeDisplayIsAll_ThenEveryProgressLineStartsWithATime(
        self, clock_testing: ClockTesting, run_logger: logging.Logger, record_capture: RecordCapture
    ) -> None:
        # Arrange
        one_step_run_scenario: OneStepRunScenario = create_random_one_step_run_scenario()
        await _run_one_step(clock_testing, run_logger, one_step_run_scenario)
        breadcrumb_formatter: BreadcrumbFormatter = BreadcrumbFormatter(time_display=TimeDisplay.ALL)
        expected_progress_line_rendered_text: ExpectedRenderedText = ExpectedRenderedText(present_patterns=[TIME_OF_DAY_AT_LINE_START])

        # Act
        actual_texts: list[str] = [breadcrumb_formatter.format(actual_log_record) for actual_log_record in record_capture.records]

        # Assert
        RenderedTextAsserter.assert_expected_and_actual_are_equal(
            expected_progress_line_rendered_text, _retrieve_text(actual_texts, one_step_run_scenario.progress_message)
        )

    @pytest.mark.parametrize("time_display", list(TimeDisplay))
    async def test_BreadcrumbFormatter_WhenAnyTimeDisplayIsChosen_ThenTheRecordsOwnMessageStaysOneCleanLine(
        self, time_display: TimeDisplay, clock_testing: ClockTesting, run_logger: logging.Logger, record_capture: RecordCapture
    ) -> None:
        # Arrange - presentation never leaks into the record, so a different handler still gets a clean message
        await _run_one_step(clock_testing, run_logger, create_random_one_step_run_scenario())
        breadcrumb_formatter: BreadcrumbFormatter = BreadcrumbFormatter(time_display=time_display)
        expected_every_message_rendered_text: ExpectedRenderedText = ExpectedRenderedText(absent_phrases=["\n", BANNER_SEPARATOR_CHARACTER * 10])

        # Act
        for actual_log_record in record_capture.records:
            breadcrumb_formatter.format(actual_log_record)

        # Assert
        EveryRenderedTextAsserter.assert_expected_and_actual_are_equal(
            expected_every_message_rendered_text, [actual_log_record.getMessage() for actual_log_record in record_capture.records]
        )


@pytest.mark.acceptance
class TestPlainRecords:
    def test_BreadcrumbFormatter_WhenARecordHasNoBreadcrumbAttributes_ThenItRendersAsItsMessage(self) -> None:
        # Arrange
        expected_text: str = create_random_log_message()
        plain_log_record: logging.LogRecord = logging.LogRecord(
            create_random_logger_name(), logging.INFO, create_random_source_path(), 1, expected_text, (), None
        )

        # Act
        actual_text: str = BreadcrumbFormatter().format(plain_log_record)

        # Assert
        assert actual_text == expected_text

    def test_BreadcrumbFormatter_WhenARecordCarriesAnException_ThenTheTracebackIsAppended(self) -> None:
        # Arrange
        exception_message: str = create_random_failure_message()
        log_record_message: str = create_random_log_message()
        plain_testing_error: PlainTestingError = PlainTestingError(exception_message)
        failed_log_record: logging.LogRecord = logging.LogRecord(
            create_random_logger_name(),
            logging.ERROR,
            create_random_source_path(),
            1,
            log_record_message,
            (),
            (type(plain_testing_error), plain_testing_error, None),
        )
        expected_rendered_text: ExpectedRenderedText = ExpectedRenderedText(
            starts_with=f"{log_record_message}\n", ends_with=f"PlainTestingError: {exception_message}"
        )

        # Act
        actual_text: str = BreadcrumbFormatter().format(failed_log_record)

        # Assert
        RenderedTextAsserter.assert_expected_and_actual_are_equal(expected_rendered_text, actual_text)
