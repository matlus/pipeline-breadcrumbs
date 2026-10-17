# Acceptance tests for how a run behaves when something goes wrong: the failing step leaves a
# breadcrumb and lets the exception escape, the exception is stamped with where it failed, a
# storage outage is its own exception, and a lost manifest never hides the failure that ended the run.

import logging
from typing import Final, NoReturn, final, override

import pytest
from breadcrumbs_acceptance_support.asserters.asserter_exception import ANY_CONTEXTUAL_VALUE, AsserterException, ExpectedException
from breadcrumbs_acceptance_support.asserters.asserter_log_record import AsserterLogRecord, ExpectedLogRecord
from breadcrumbs_acceptance_support.asserters.asserter_step_boundaries import AsserterStepBoundaries, ExpectedStepBoundary
from breadcrumbs_acceptance_support.clock_testing import ClockTesting
from breadcrumbs_acceptance_support.data_generators import create_random_pipeline_name, create_random_work_item
from breadcrumbs_acceptance_support.exceptions_testing import DiagnosticTestingError, PlainTestingError

from pipeline_breadcrumbs import Artifact, ArtifactKind, ArtifactSinkError, ArtifactSinkProtocol, AttributeKey, EventKind, PipelineRun, Step, WorkItem
from pipeline_breadcrumbs.testing import ArtifactSinkTesting, RecordCapture

METADATA_AUDIT: Final[Step] = Step(2, "Metadata Audit")
CLASSIFICATION: Final[Step] = Step(3, "Classification")
SCORE_SECTIONS: Final[Step] = Step(2, "Score Sections")
PAGE_EVIDENCE: Final[ArtifactKind] = ArtifactKind("page_evidence", "json", "application/json")
STORAGE_OUTAGE_MESSAGE: Final[str] = "blob storage unreachable"
MANIFEST_FILENAME: Final[str] = "manifest.json"


@final
class ArtifactSinkUnreachable(ArtifactSinkProtocol):
    @override
    async def persist(self, artifact: Artifact) -> None:
        raise ConnectionError(STORAGE_OUTAGE_MESSAGE)


def _advance_then_fail(clock_testing: ClockTesting, elapsed_seconds: float, failure_message: str) -> NoReturn:
    clock_testing.advance(elapsed_seconds)
    raise PlainTestingError(failure_message)


@pytest.mark.acceptance
class TestFailingStep:
    async def test_PipelineRun_WhenAStepRaises_ThenItLogsAFailedBreadcrumbAndTheExceptionEscapes(
        self, clock_testing: ClockTesting, artifact_sink_testing: ArtifactSinkTesting, run_logger: logging.Logger, record_capture: RecordCapture
    ) -> None:
        # Arrange
        pipeline_name: str = create_random_pipeline_name()
        work_item: WorkItem = create_random_work_item()
        expected_elapsed_seconds: float = 1.25
        expected_failure_message: str = "bad json"
        pipeline_run: PipelineRun = PipelineRun(
            pipeline_name=pipeline_name, artifact_sink=artifact_sink_testing, logger=run_logger, supplied_clock=clock_testing.clock
        )
        expected_exception: ExpectedException = ExpectedException(PlainTestingError, message_phrases=[expected_failure_message])
        expected_step_number: str = "2"
        expected_step_boundaries: list[ExpectedStepBoundary] = [
            ExpectedStepBoundary(expected_step_number, "STARTED"),
            ExpectedStepBoundary(expected_step_number, "FAILED", elapsed_seconds=expected_elapsed_seconds),
        ]
        # The traceback is logged once, by the host's outer boundary; a step never repeats it.
        expected_failed_log_record: ExpectedLogRecord = ExpectedLogRecord(
            level=logging.WARNING,
            attribute_value_by_key={AttributeKey.FAILURE_TYPE: "PlainTestingError", AttributeKey.FAILURE_MESSAGE: expected_failure_message},
            carries_traceback=False,
        )

        # Act
        with pytest.raises(PlainTestingError) as actual_raised:
            async with pipeline_run, pipeline_run.open_work_item(work_item) as work_item_scope, work_item_scope.step(METADATA_AUDIT):
                _advance_then_fail(clock_testing, expected_elapsed_seconds, expected_failure_message)

        # Assert
        AsserterException.assert_exception(expected_exception, actual_raised.value)
        AsserterStepBoundaries.assert_exactly_these_step_boundaries(expected_step_boundaries, record_capture.records)
        AsserterLogRecord.assert_record(expected_failed_log_record, record_capture.boundaries(EventKind.STEP)[-1])

    async def test_PipelineRun_WhenADiagnosticExceptionEscapesANestedStep_ThenTheInnermostStepIsStampedOntoItOnce(
        self, artifact_sink_testing: ArtifactSinkTesting, run_logger: logging.Logger
    ) -> None:
        # Arrange
        pipeline_name: str = create_random_pipeline_name()
        work_item: WorkItem = create_random_work_item()
        failure_message: str = "response was not json"
        pipeline_run: PipelineRun = PipelineRun(pipeline_name=pipeline_name, artifact_sink=artifact_sink_testing, logger=run_logger)
        # The child step stamps first; the parent finds the stamp and leaves it alone.
        expected_exception: ExpectedException = ExpectedException(
            DiagnosticTestingError,
            message_phrases=[failure_message],
            contextual_data_by_name={"FailedAtStepNumber": "3.2", "FailedAtStepName": "Score Sections", "FailedAtStepKey": "score_sections"},
        )

        # Act
        with pytest.raises(DiagnosticTestingError) as actual_raised:
            async with (
                pipeline_run,
                pipeline_run.open_work_item(work_item) as work_item_scope,
                work_item_scope.step(CLASSIFICATION) as parent_step_scope,
                parent_step_scope.step(SCORE_SECTIONS),
            ):
                raise DiagnosticTestingError(failure_message)

        # Assert
        AsserterException.assert_exception(expected_exception, actual_raised.value)

    async def test_PipelineRun_WhenTheExceptionCarriesNoDiagnosticData_ThenItPassesThroughUntouched(
        self, artifact_sink_testing: ArtifactSinkTesting, run_logger: logging.Logger
    ) -> None:
        # Arrange
        pipeline_name: str = create_random_pipeline_name()
        work_item: WorkItem = create_random_work_item()
        plain_testing_error: PlainTestingError = PlainTestingError("missing")
        pipeline_run: PipelineRun = PipelineRun(pipeline_name=pipeline_name, artifact_sink=artifact_sink_testing, logger=run_logger)

        # Act
        with pytest.raises(PlainTestingError) as actual_raised:
            async with pipeline_run, pipeline_run.open_work_item(work_item) as work_item_scope, work_item_scope.step(METADATA_AUDIT):
                raise plain_testing_error

        # Assert - the very instance the step raised reaches the caller
        assert actual_raised.value is plain_testing_error


@pytest.mark.acceptance
class TestFailingSink:
    async def test_PipelineRun_WhenTheSinkFailsOnEmit_ThenAnArtifactSinkErrorNamesTheArtifactAndKeepsTheCause(
        self, run_logger: logging.Logger
    ) -> None:
        # Arrange
        pipeline_name: str = create_random_pipeline_name()
        work_item: WorkItem = create_random_work_item()
        expected_artifact_kind_key: str = PAGE_EVIDENCE.key
        expected_artifact_filename: str = f"{work_item.stem}_step_02_{expected_artifact_kind_key}.json"
        pipeline_run: PipelineRun = PipelineRun(pipeline_name=pipeline_name, artifact_sink=ArtifactSinkUnreachable(), logger=run_logger)
        expected_exception: ExpectedException = ExpectedException(
            ArtifactSinkError,
            message_phrases=[expected_artifact_filename],
            contextual_data_by_name={
                "ExceptionType": "ArtifactSinkError",
                "ArtifactKind": expected_artifact_kind_key,
                "ArtifactFilename": expected_artifact_filename,
                "ArtifactBytes": 2,
                "FailedAtStepNumber": "2",
                "FailedAtStepName": "Metadata Audit",
                "FailedAtStepKey": "metadata_audit",
            },
            cause_type=ConnectionError,
        )

        # Act
        with pytest.raises(ArtifactSinkError) as actual_raised:
            async with pipeline_run, pipeline_run.open_work_item(work_item) as work_item_scope, work_item_scope.step(METADATA_AUDIT) as step_scope:
                await step_scope.emit(PAGE_EVIDENCE, b"{}")

        # Assert
        AsserterException.assert_exception(expected_exception, actual_raised.value)

    async def test_PipelineRun_WhenTheManifestCannotBeWrittenWhileTheRunIsFailing_ThenTheOriginalFailureIsNotHidden(
        self, run_logger: logging.Logger
    ) -> None:
        # Arrange
        pipeline_name: str = create_random_pipeline_name()
        real_problem_message: str = "the real problem"
        pipeline_run: PipelineRun = PipelineRun(pipeline_name=pipeline_name, artifact_sink=ArtifactSinkUnreachable(), logger=run_logger)
        expected_exception: ExpectedException = ExpectedException(
            PlainTestingError, message_phrases=[real_problem_message], note_phrases=["run manifest could not be persisted", MANIFEST_FILENAME]
        )

        # Act
        with pytest.raises(PlainTestingError) as actual_raised:
            async with pipeline_run:
                raise PlainTestingError(real_problem_message)

        # Assert - the run's own failure, not the storage outage, reaches the caller, carrying the lost manifest as a note
        AsserterException.assert_exception(expected_exception, actual_raised.value)

    async def test_PipelineRun_WhenTheManifestCannotBeWrittenAndNothingElseFailed_ThenTheOutageIsReported(self, run_logger: logging.Logger) -> None:
        # Arrange
        pipeline_name: str = create_random_pipeline_name()
        pipeline_run: PipelineRun = PipelineRun(pipeline_name=pipeline_name, artifact_sink=ArtifactSinkUnreachable(), logger=run_logger)
        expected_exception: ExpectedException = ExpectedException(
            ArtifactSinkError,
            message_phrases=[MANIFEST_FILENAME],
            contextual_data_by_name={
                "ExceptionType": "ArtifactSinkError",
                "ArtifactKind": "manifest",
                "ArtifactFilename": MANIFEST_FILENAME,
                "ArtifactBytes": ANY_CONTEXTUAL_VALUE,
            },
            cause_type=ConnectionError,
        )

        # Act
        with pytest.raises(ArtifactSinkError) as actual_raised:
            async with pipeline_run:
                pass

        # Assert
        AsserterException.assert_exception(expected_exception, actual_raised.value)


@pytest.mark.acceptance
class TestRunSummary:
    async def test_PipelineRun_WhenOneWorkItemFails_ThenTheRunSummaryCountsItAndIsLoggedAsAWarning(
        self, artifact_sink_testing: ArtifactSinkTesting, run_logger: logging.Logger, record_capture: RecordCapture
    ) -> None:
        # Arrange
        pipeline_name: str = create_random_pipeline_name()
        healthy_work_item: WorkItem = create_random_work_item()
        failing_work_item: WorkItem = create_random_work_item()
        pipeline_run: PipelineRun = PipelineRun(pipeline_name=pipeline_name, artifact_sink=artifact_sink_testing, logger=run_logger)
        expected_run_summary_log_record: ExpectedLogRecord = ExpectedLogRecord(
            level=logging.WARNING,
            attribute_value_by_key={AttributeKey.OUTCOME: "2 work item(s): 1 complete, 1 failed", AttributeKey.STATUS: "FAILED"},
        )

        # Act
        async with pipeline_run:
            async with pipeline_run.open_work_item(healthy_work_item) as work_item_scope, work_item_scope.step(METADATA_AUDIT):
                pass
            with pytest.raises(PlainTestingError):
                async with pipeline_run.open_work_item(failing_work_item):
                    raise PlainTestingError("boom")

        # Assert
        AsserterLogRecord.assert_record(expected_run_summary_log_record, record_capture.boundaries(EventKind.RUN)[-1])
