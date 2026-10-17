# Acceptance tests for the trail a run leaves: step boundaries, progress lines and the attributes
# every record carries. Black-box through PipelineRun, the way a pipeline uses the library; the
# observations are the log records the run wrote and the artifacts it handed to the sink.

import logging
import secrets
from collections.abc import Iterable
from typing import Final

import pytest
from breadcrumbs_acceptance_support.asserters.asserter_artifacts import AsserterArtifacts
from breadcrumbs_acceptance_support.asserters.asserter_exception import AsserterException, ExpectedException
from breadcrumbs_acceptance_support.asserters.asserter_log_record import AsserterLogRecord, ExpectedLogRecord
from breadcrumbs_acceptance_support.asserters.asserter_step_boundaries import AsserterStepBoundaries, ExpectedStepBoundary
from breadcrumbs_acceptance_support.clock_testing import ClockTesting
from breadcrumbs_acceptance_support.data_generators import (
    create_random_attribute_name,
    create_random_outcome,
    create_random_pipeline_name,
    create_random_progress_message,
    create_random_skip_reason,
    create_random_work_item,
)

from pipeline_breadcrumbs import ArtifactKind, AttributeKey, EventKind, InvalidDeclarationError, PipelineRun, Step, WorkItem
from pipeline_breadcrumbs.testing import ArtifactSinkTesting, RecordCapture

MANIFEST_FILENAME: Final[str] = "manifest.json"
PAGE_IMAGE_EXTRACTION: Final[Step] = Step(1, "Page Image Extraction")
METADATA_AUDIT: Final[Step] = Step(2, "Metadata Audit")
CLASSIFICATION: Final[Step] = Step(3, "Classification")
SCORE_SECTIONS: Final[Step] = Step(2, "Score Sections")
RECONCILE_SCORES: Final[Step] = Step(3, "Reconcile")
PAGE_EVIDENCE: Final[ArtifactKind] = ArtifactKind("page_evidence", "json", "application/json")
_RANDOM_SUFFIX_BYTES: Final[int] = 4


def _retrieve_record(actual_log_records: Iterable[logging.LogRecord], expected_message: str) -> logging.LogRecord:
    return next(actual_log_record for actual_log_record in actual_log_records if actual_log_record.getMessage() == expected_message)


@pytest.mark.acceptance
class TestStepBoundaries:
    async def test_PipelineRun_WhenAStepRuns_ThenItAnnouncesItselfAndReportsItsElapsedTime(
        self, clock_testing: ClockTesting, artifact_sink_testing: ArtifactSinkTesting, run_logger: logging.Logger, record_capture: RecordCapture
    ) -> None:
        # Arrange
        pipeline_name: str = create_random_pipeline_name()
        work_item: WorkItem = create_random_work_item()
        expected_elapsed_seconds: float = 2.5
        expected_step_number: str = "1"
        pipeline_run: PipelineRun = PipelineRun(
            pipeline_name=pipeline_name, artifact_sink=artifact_sink_testing, logger=run_logger, supplied_clock=clock_testing.clock
        )
        expected_step_boundaries: list[ExpectedStepBoundary] = [
            ExpectedStepBoundary(expected_step_number, "STARTED"),
            ExpectedStepBoundary(expected_step_number, "COMPLETE", elapsed_seconds=expected_elapsed_seconds),
        ]
        expected_completion_log_record: ExpectedLogRecord = ExpectedLogRecord(
            message=f"Step {expected_step_number} Page Image Extraction complete in 2.500s",
            attribute_value_by_key={AttributeKey.STEP_KEY: "page_image_extraction"},
        )

        # Act
        async with pipeline_run, pipeline_run.open_work_item(work_item) as work_item_scope, work_item_scope.step(PAGE_IMAGE_EXTRACTION):
            clock_testing.advance(expected_elapsed_seconds)

        # Assert
        AsserterStepBoundaries.assert_exactly_these_step_boundaries(expected_step_boundaries, record_capture.records)
        AsserterLogRecord.assert_record(expected_completion_log_record, record_capture.boundaries(EventKind.STEP)[-1])

    async def test_PipelineRun_WhenAStepSetsItsOutcome_ThenTheOutcomeIsPartOfTheCompletionRecord(
        self, artifact_sink_testing: ArtifactSinkTesting, run_logger: logging.Logger, record_capture: RecordCapture
    ) -> None:
        # Arrange
        pipeline_name: str = create_random_pipeline_name()
        work_item: WorkItem = create_random_work_item()
        pipeline_run: PipelineRun = PipelineRun(pipeline_name=pipeline_name, artifact_sink=artifact_sink_testing, logger=run_logger)
        expected_outcome: str = create_random_outcome()
        expected_start_count: int = 5
        expected_completion_log_record: ExpectedLogRecord = ExpectedLogRecord(
            message_suffix=f": {expected_outcome}",
            attribute_value_by_key={AttributeKey.OUTCOME: expected_outcome, f"{AttributeKey.DETAIL_PREFIX}starts": expected_start_count},
        )

        # Act
        async with pipeline_run, pipeline_run.open_work_item(work_item) as work_item_scope, work_item_scope.step(METADATA_AUDIT) as step_scope:
            step_scope.outcome(expected_outcome, starts=expected_start_count)

        # Assert
        AsserterLogRecord.assert_record(expected_completion_log_record, record_capture.boundaries(EventKind.STEP)[-1])

    async def test_PipelineRun_WhenAStepOpensAChildStep_ThenTheChildsNumberComposesUnderTheParents(
        self, artifact_sink_testing: ArtifactSinkTesting, run_logger: logging.Logger, record_capture: RecordCapture
    ) -> None:
        # Arrange
        pipeline_name: str = create_random_pipeline_name()
        work_item: WorkItem = create_random_work_item()
        expected_parent_step_number: str = "3"
        expected_child_step_number: str = "3.2"
        pipeline_run: PipelineRun = PipelineRun(pipeline_name=pipeline_name, artifact_sink=artifact_sink_testing, logger=run_logger)
        expected_step_boundaries: list[ExpectedStepBoundary] = [
            ExpectedStepBoundary(expected_parent_step_number, "STARTED"),
            ExpectedStepBoundary(expected_child_step_number, "STARTED"),
            ExpectedStepBoundary(expected_child_step_number, "COMPLETE"),
            ExpectedStepBoundary(expected_parent_step_number, "COMPLETE"),
        ]
        expected_filenames: list[str] = [f"{work_item.stem}_step_03.02_page_evidence.json", MANIFEST_FILENAME]

        # Act
        async with (
            pipeline_run,
            pipeline_run.open_work_item(work_item) as work_item_scope,
            work_item_scope.step(CLASSIFICATION) as parent_step_scope,
            parent_step_scope.step(SCORE_SECTIONS) as child_step_scope,
        ):
            await child_step_scope.emit(PAGE_EVIDENCE, b"{}")

        # Assert
        AsserterStepBoundaries.assert_exactly_these_step_boundaries(expected_step_boundaries, record_capture.records)
        AsserterArtifacts.assert_exactly_these_filenames_in_order(expected_filenames, artifact_sink_testing.artifacts)

    async def test_PipelineRun_WhenAChildStepIsSkipped_ThenTheSkipIsRecordedWithItsReason(
        self, artifact_sink_testing: ArtifactSinkTesting, run_logger: logging.Logger, record_capture: RecordCapture
    ) -> None:
        # Arrange
        pipeline_name: str = create_random_pipeline_name()
        work_item: WorkItem = create_random_work_item()
        skip_reason: str = create_random_skip_reason()
        expected_child_step_number: str = "3.3"
        pipeline_run: PipelineRun = PipelineRun(pipeline_name=pipeline_name, artifact_sink=artifact_sink_testing, logger=run_logger)
        expected_skipped_log_record: ExpectedLogRecord = ExpectedLogRecord(
            message=f"Step {expected_child_step_number} Reconcile skipped: {skip_reason}",
            attribute_value_by_key={AttributeKey.STATUS: "SKIPPED", AttributeKey.STEP_NUMBER: expected_child_step_number},
        )

        # Act
        async with pipeline_run, pipeline_run.open_work_item(work_item) as work_item_scope, work_item_scope.step(CLASSIFICATION) as parent_step_scope:
            parent_step_scope.skipped(RECONCILE_SCORES, skip_reason)

        # Assert
        AsserterLogRecord.assert_record(expected_skipped_log_record, record_capture.boundaries(EventKind.STEP)[1])


@pytest.mark.acceptance
class TestProgressLinesAndAttributes:
    async def test_PipelineRun_WhenAStepReportsProgress_ThenTheDetailsAreNamespacedAttributes(
        self, artifact_sink_testing: ArtifactSinkTesting, run_logger: logging.Logger, record_capture: RecordCapture
    ) -> None:
        # Arrange
        pipeline_name: str = create_random_pipeline_name()
        work_item: WorkItem = create_random_work_item()
        expected_progress_message: str = create_random_progress_message()
        expected_page_count: int = 14
        expected_concurrency: int = 5
        pipeline_run: PipelineRun = PipelineRun(pipeline_name=pipeline_name, artifact_sink=artifact_sink_testing, logger=run_logger)
        # A progress line is not a boundary, so it carries no event attribute.
        expected_progress_log_record: ExpectedLogRecord = ExpectedLogRecord(
            attribute_value_by_key={
                f"{AttributeKey.DETAIL_PREFIX}pages": expected_page_count,
                f"{AttributeKey.DETAIL_PREFIX}concurrency": expected_concurrency,
            },
            absent_attribute_keys=[AttributeKey.EVENT],
        )

        # Act
        async with pipeline_run, pipeline_run.open_work_item(work_item) as work_item_scope, work_item_scope.step(METADATA_AUDIT) as step_scope:
            step_scope.info(expected_progress_message, pages=expected_page_count, concurrency=expected_concurrency)

        # Assert
        AsserterLogRecord.assert_record(expected_progress_log_record, _retrieve_record(record_capture.records, expected_progress_message))

    async def test_PipelineRun_WhenAFieldIsNamedLikeALogRecordAttribute_ThenLoggingStillWorks(
        self, artifact_sink_testing: ArtifactSinkTesting, run_logger: logging.Logger, record_capture: RecordCapture
    ) -> None:
        # Arrange
        pipeline_name: str = create_random_pipeline_name()
        work_item: WorkItem = create_random_work_item()
        expected_progress_message: str = create_random_progress_message()
        expected_name_detail: str = f"Contract {secrets.token_hex(_RANDOM_SUFFIX_BYTES)}"
        pipeline_run: PipelineRun = PipelineRun(pipeline_name=pipeline_name, artifact_sink=artifact_sink_testing, logger=run_logger)
        expected_progress_log_record: ExpectedLogRecord = ExpectedLogRecord(
            attribute_value_by_key={f"{AttributeKey.DETAIL_PREFIX}name": expected_name_detail}
        )

        # Act - `name`, `message` and `filename` are LogRecord attributes the standard library refuses as `extra` keys
        async with pipeline_run, pipeline_run.open_work_item(work_item) as work_item_scope, work_item_scope.step(METADATA_AUDIT) as step_scope:
            step_scope.info(expected_progress_message, name=expected_name_detail, message="x", filename="a.pdf")

        # Assert
        AsserterLogRecord.assert_record(expected_progress_log_record, _retrieve_record(record_capture.records, expected_progress_message))

    async def test_PipelineRun_WhenCallerAttributesAreGiven_ThenEveryRecordCarriesThem(
        self, artifact_sink_testing: ArtifactSinkTesting, run_logger: logging.Logger, record_capture: RecordCapture
    ) -> None:
        # Arrange
        pipeline_name: str = create_random_pipeline_name()
        work_item: WorkItem = create_random_work_item()
        expected_trace_id: str = secrets.token_hex(_RANDOM_SUFFIX_BYTES)
        trace_id_attribute_name: str = create_random_attribute_name()
        pipeline_run: PipelineRun = PipelineRun(
            pipeline_name=pipeline_name,
            artifact_sink=artifact_sink_testing,
            logger=run_logger,
            attributes={trace_id_attribute_name: expected_trace_id},
        )
        expected_attribute_value_by_key: dict[str, object] = {
            trace_id_attribute_name: expected_trace_id,
            AttributeKey.PIPELINE_NAME: pipeline_name,
            AttributeKey.RUN_ID: pipeline_run.run_id,
        }

        # Act
        async with pipeline_run, pipeline_run.open_work_item(work_item) as work_item_scope, work_item_scope.step(METADATA_AUDIT) as step_scope:
            step_scope.info(create_random_progress_message())
            await step_scope.emit(PAGE_EVIDENCE, b"{}")

        # Assert
        AsserterLogRecord.assert_every_record_carries(expected_attribute_value_by_key, record_capture.records)

    async def test_PipelineRun_WhenAStepRecordIsWritten_ThenItCarriesTheWorkItemsIdentity(
        self, artifact_sink_testing: ArtifactSinkTesting, run_logger: logging.Logger, record_capture: RecordCapture
    ) -> None:
        # Arrange
        pipeline_name: str = create_random_pipeline_name()
        work_item: WorkItem = create_random_work_item()
        pipeline_run: PipelineRun = PipelineRun(pipeline_name=pipeline_name, artifact_sink=artifact_sink_testing, logger=run_logger)
        expected_step_log_record: ExpectedLogRecord = ExpectedLogRecord(
            attribute_value_by_key={AttributeKey.WORK_ITEM_ID: work_item.id, AttributeKey.WORK_ITEM_NAME: work_item.name}
        )

        # Act
        async with pipeline_run, pipeline_run.open_work_item(work_item) as work_item_scope, work_item_scope.step(METADATA_AUDIT):
            pass

        # Assert
        AsserterLogRecord.assert_record(expected_step_log_record, record_capture.boundaries(EventKind.STEP)[0])

    def test_PipelineRun_WhenCallerAttributesShadowALogRecordAttribute_ThenTheRunIsRefused(self, artifact_sink_testing: ArtifactSinkTesting) -> None:
        # Arrange
        pipeline_name: str = create_random_pipeline_name()
        shadowing_attribute_name: str = "name"
        expected_exception: ExpectedException = ExpectedException(
            InvalidDeclarationError, message_phrases=["reserved logging attribute names", shadowing_attribute_name]
        )

        # Act
        with pytest.raises(InvalidDeclarationError) as actual_raised:
            PipelineRun(pipeline_name=pipeline_name, artifact_sink=artifact_sink_testing, attributes={shadowing_attribute_name: "x"})

        # Assert
        AsserterException.assert_exception(expected_exception, actual_raised.value)

    def test_PipelineRun_WhenTheNameIsBlank_ThenTheRunIsRefused(self, artifact_sink_testing: ArtifactSinkTesting) -> None:
        # Arrange
        blank_pipeline_name: str = " "
        expected_exception: ExpectedException = ExpectedException(InvalidDeclarationError, message_phrases=["needs a name"])

        # Act
        with pytest.raises(InvalidDeclarationError) as actual_raised:
            PipelineRun(pipeline_name=blank_pipeline_name, artifact_sink=artifact_sink_testing)

        # Assert
        AsserterException.assert_exception(expected_exception, actual_raised.value)
