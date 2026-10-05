# Acceptance tests for the trail a run leaves: step boundaries, progress lines and the attributes
# every record carries. Black-box through PipelineRun, the way a pipeline uses the library; the
# observations are the log records the run wrote and the artifacts it handed to the sink.

import logging
from typing import Final

import pytest
from breadcrumbs_acceptance_support.asserters.asserter_artifacts import AsserterArtifacts
from breadcrumbs_acceptance_support.asserters.asserter_step_boundaries import AsserterStepBoundaries, ExpectedStepBoundary
from breadcrumbs_acceptance_support.clock_testing import ClockTesting
from breadcrumbs_acceptance_support.data_generators import create_random_work_item

from pipeline_breadcrumbs import ArtifactKind, AttributeKey, EventKind, PipelineRun, Step, WorkItem
from pipeline_breadcrumbs.testing import ArtifactRecorder, RecordCapture

PAGE_IMAGE_EXTRACTION: Final[Step] = Step(1, "Page Image Extraction")
METADATA_AUDIT: Final[Step] = Step(2, "Metadata Audit")
CLASSIFICATION: Final[Step] = Step(3, "Classification")
SCORE_SECTIONS: Final[Step] = Step(2, "Score Sections")
RECONCILE_SCORES: Final[Step] = Step(3, "Reconcile")
PAGE_EVIDENCE: Final[ArtifactKind] = ArtifactKind("page_evidence", "json", "application/json")


def _find_record(actual_log_records: list[logging.LogRecord], expected_message: str) -> logging.LogRecord:
    return next(actual_log_record for actual_log_record in actual_log_records if actual_log_record.getMessage() == expected_message)


@pytest.mark.acceptance
class TestStepBoundaries:
    async def test_PipelineRun_WhenAStepRuns_ThenItAnnouncesItselfAndReportsItsElapsedTime(
        self, clock_testing: ClockTesting, artifact_recorder: ArtifactRecorder, run_logger: logging.Logger, record_capture: RecordCapture
    ) -> None:
        # Arrange
        work_item: WorkItem = create_random_work_item()
        expected_elapsed_seconds: float = 2.5
        expected_step_number: str = "1"
        pipeline_run: PipelineRun = PipelineRun(pipeline_name="demo", sink=artifact_recorder, logger=run_logger, clock=clock_testing.clock)

        # Act
        async with pipeline_run, pipeline_run.open_work_item(work_item) as work_item_scope, work_item_scope.step(PAGE_IMAGE_EXTRACTION):
            clock_testing.advance(expected_elapsed_seconds)

        # Assert
        AsserterStepBoundaries.assert_exactly_these_step_boundaries(
            [
                ExpectedStepBoundary(expected_step_number, "STARTED"),
                ExpectedStepBoundary(expected_step_number, "COMPLETE", elapsed_seconds=expected_elapsed_seconds),
            ],
            record_capture.records,
        )
        actual_completion_record: logging.LogRecord = record_capture.boundaries(EventKind.STEP)[-1]
        expected_message: str = f"Step {expected_step_number} Page Image Extraction complete in 2.500s"
        assert actual_completion_record.getMessage() == expected_message
        assert RecordCapture.attribute(actual_completion_record, AttributeKey.STEP_KEY) == "page_image_extraction"

    async def test_PipelineRun_WhenAStepSetsItsOutcome_ThenTheOutcomeIsPartOfTheCompletionRecord(
        self, artifact_recorder: ArtifactRecorder, run_logger: logging.Logger, record_capture: RecordCapture
    ) -> None:
        # Arrange
        work_item: WorkItem = create_random_work_item()
        pipeline_run: PipelineRun = PipelineRun(pipeline_name="demo", sink=artifact_recorder, logger=run_logger)

        # Act
        async with pipeline_run, pipeline_run.open_work_item(work_item) as work_item_scope, work_item_scope.step(METADATA_AUDIT) as step_scope:
            step_scope.outcome("Found 5 write-up starts", starts=5)

        # Assert
        actual_completion_record: logging.LogRecord = record_capture.boundaries(EventKind.STEP)[-1]
        expected_outcome: str = "Found 5 write-up starts"
        assert actual_completion_record.getMessage().endswith(f": {expected_outcome}")
        assert RecordCapture.attribute(actual_completion_record, AttributeKey.OUTCOME) == expected_outcome
        assert RecordCapture.attribute(actual_completion_record, f"{AttributeKey.DETAIL_PREFIX}starts") == 5

    async def test_PipelineRun_WhenAStepOpensAChildStep_ThenTheChildsNumberComposesUnderTheParents(
        self, artifact_recorder: ArtifactRecorder, run_logger: logging.Logger, record_capture: RecordCapture
    ) -> None:
        # Arrange
        work_item: WorkItem = create_random_work_item()
        expected_parent_step_number: str = "3"
        expected_child_step_number: str = "3.2"
        pipeline_run: PipelineRun = PipelineRun(pipeline_name="demo", sink=artifact_recorder, logger=run_logger)

        # Act
        async with (
            pipeline_run,
            pipeline_run.open_work_item(work_item) as work_item_scope,
            work_item_scope.step(CLASSIFICATION) as parent_step_scope,
            parent_step_scope.step(SCORE_SECTIONS) as child_step_scope,
        ):
            await child_step_scope.emit(PAGE_EVIDENCE, b"{}")

        # Assert
        AsserterStepBoundaries.assert_exactly_these_step_boundaries(
            [
                ExpectedStepBoundary(expected_parent_step_number, "STARTED"),
                ExpectedStepBoundary(expected_child_step_number, "STARTED"),
                ExpectedStepBoundary(expected_child_step_number, "COMPLETE"),
                ExpectedStepBoundary(expected_parent_step_number, "COMPLETE"),
            ],
            record_capture.records,
        )
        AsserterArtifacts.assert_exactly_these_filenames_in_order(
            [f"{work_item.stem}_step_03.02_page_evidence.json", "manifest.json"], artifact_recorder.artifacts
        )

    async def test_PipelineRun_WhenAChildStepIsSkipped_ThenTheSkipIsRecordedWithItsReason(
        self, artifact_recorder: ArtifactRecorder, run_logger: logging.Logger, record_capture: RecordCapture
    ) -> None:
        # Arrange
        work_item: WorkItem = create_random_work_item()
        pipeline_run: PipelineRun = PipelineRun(pipeline_name="demo", sink=artifact_recorder, logger=run_logger)

        # Act
        async with pipeline_run, pipeline_run.open_work_item(work_item) as work_item_scope, work_item_scope.step(CLASSIFICATION) as parent_step_scope:
            parent_step_scope.skipped(RECONCILE_SCORES, "no low-confidence sections")

        # Assert
        actual_skipped_record: logging.LogRecord = record_capture.boundaries(EventKind.STEP)[1]
        assert RecordCapture.attribute(actual_skipped_record, AttributeKey.STATUS) == "SKIPPED"
        assert RecordCapture.attribute(actual_skipped_record, AttributeKey.STEP_NUMBER) == "3.3"
        expected_message: str = "Step 3.3 Reconcile skipped: no low-confidence sections"
        assert actual_skipped_record.getMessage() == expected_message


@pytest.mark.acceptance
class TestProgressLinesAndAttributes:
    async def test_PipelineRun_WhenAStepReportsProgress_ThenTheDetailsAreNamespacedAttributes(
        self, artifact_recorder: ArtifactRecorder, run_logger: logging.Logger, record_capture: RecordCapture
    ) -> None:
        # Arrange
        work_item: WorkItem = create_random_work_item()
        expected_progress_message: str = "Auditing metadata"
        pipeline_run: PipelineRun = PipelineRun(pipeline_name="demo", sink=artifact_recorder, logger=run_logger)

        # Act
        async with pipeline_run, pipeline_run.open_work_item(work_item) as work_item_scope, work_item_scope.step(METADATA_AUDIT) as step_scope:
            step_scope.info(expected_progress_message, pages=14, concurrency=5)

        # Assert
        actual_progress_record: logging.LogRecord = _find_record(record_capture.records, expected_progress_message)
        assert RecordCapture.attribute(actual_progress_record, f"{AttributeKey.DETAIL_PREFIX}pages") == 14
        assert RecordCapture.attribute(actual_progress_record, f"{AttributeKey.DETAIL_PREFIX}concurrency") == 5
        assert AttributeKey.EVENT not in actual_progress_record.__dict__

    async def test_PipelineRun_WhenAFieldIsNamedLikeALogRecordAttribute_ThenLoggingStillWorks(
        self, artifact_recorder: ArtifactRecorder, run_logger: logging.Logger, record_capture: RecordCapture
    ) -> None:
        # Arrange
        work_item: WorkItem = create_random_work_item()
        expected_progress_message: str = "Reading"
        pipeline_run: PipelineRun = PipelineRun(pipeline_name="demo", sink=artifact_recorder, logger=run_logger)

        # Act - `name`, `message` and `filename` are LogRecord attributes the standard library refuses as `extra` keys
        async with pipeline_run, pipeline_run.open_work_item(work_item) as work_item_scope, work_item_scope.step(METADATA_AUDIT) as step_scope:
            step_scope.info(expected_progress_message, name="Contract 12", message="x", filename="a.pdf")

        # Assert
        actual_progress_record: logging.LogRecord = _find_record(record_capture.records, expected_progress_message)
        assert RecordCapture.attribute(actual_progress_record, f"{AttributeKey.DETAIL_PREFIX}name") == "Contract 12"

    async def test_PipelineRun_WhenCallerAttributesAreGiven_ThenEveryRecordCarriesThem(
        self, artifact_recorder: ArtifactRecorder, run_logger: logging.Logger, record_capture: RecordCapture
    ) -> None:
        # Arrange
        work_item: WorkItem = create_random_work_item()
        expected_trace_id: str = "abc123"
        trace_id_attribute_name: str = "trace_id"
        pipeline_run: PipelineRun = PipelineRun(
            pipeline_name="demo", sink=artifact_recorder, logger=run_logger, attributes={trace_id_attribute_name: expected_trace_id}
        )

        # Act
        async with pipeline_run, pipeline_run.open_work_item(work_item) as work_item_scope, work_item_scope.step(METADATA_AUDIT) as step_scope:
            step_scope.info("Working")
            await step_scope.emit(PAGE_EVIDENCE, b"{}")

        # Assert
        assert record_capture.records
        for actual_log_record in record_capture.records:
            assert RecordCapture.attribute(actual_log_record, trace_id_attribute_name) == expected_trace_id
            assert RecordCapture.attribute(actual_log_record, AttributeKey.PIPELINE_NAME) == "demo"
            assert RecordCapture.attribute(actual_log_record, AttributeKey.RUN_ID) == pipeline_run.run_id

    async def test_PipelineRun_WhenAStepRecordIsWritten_ThenItCarriesTheWorkItemsIdentity(
        self, artifact_recorder: ArtifactRecorder, run_logger: logging.Logger, record_capture: RecordCapture
    ) -> None:
        # Arrange
        work_item: WorkItem = create_random_work_item()
        pipeline_run: PipelineRun = PipelineRun(pipeline_name="demo", sink=artifact_recorder, logger=run_logger)

        # Act
        async with pipeline_run, pipeline_run.open_work_item(work_item) as work_item_scope, work_item_scope.step(METADATA_AUDIT):
            pass

        # Assert
        actual_step_record: logging.LogRecord = record_capture.boundaries(EventKind.STEP)[0]
        assert RecordCapture.attribute(actual_step_record, AttributeKey.WORK_ITEM_ID) == work_item.id
        assert RecordCapture.attribute(actual_step_record, AttributeKey.WORK_ITEM_NAME) == work_item.name

    def test_PipelineRun_WhenCallerAttributesShadowALogRecordAttribute_ThenTheRunIsRefused(self, artifact_recorder: ArtifactRecorder) -> None:
        # Arrange / Act / Assert
        with pytest.raises(ValueError, match="reserved logging attribute names"):
            PipelineRun(pipeline_name="demo", sink=artifact_recorder, attributes={"name": "x"})

    def test_PipelineRun_WhenTheNameIsBlank_ThenTheRunIsRefused(self, artifact_recorder: ArtifactRecorder) -> None:
        # Arrange / Act / Assert
        with pytest.raises(ValueError, match="needs a name"):
            PipelineRun(pipeline_name=" ", sink=artifact_recorder)
