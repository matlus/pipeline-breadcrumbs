# Acceptance tests for how a run behaves when something goes wrong: the failing step leaves a
# breadcrumb and lets the exception escape, the exception is stamped with where it failed, a
# storage outage is its own exception, and a lost manifest never hides the failure that ended the run.

import logging
from typing import Final, final, override

import pytest
from breadcrumbs_acceptance_support.asserters.asserter_contextual_data import AsserterContextualData
from breadcrumbs_acceptance_support.asserters.asserter_step_boundaries import AsserterStepBoundaries, ExpectedStepBoundary
from breadcrumbs_acceptance_support.clock_testing import ClockTesting
from breadcrumbs_acceptance_support.data_generators import create_random_work_item
from breadcrumbs_acceptance_support.exceptions_testing import DiagnosticTestingError

from pipeline_breadcrumbs import Artifact, ArtifactKind, ArtifactSinkError, ArtifactSinkProtocol, AttributeKey, EventKind, PipelineRun, Step, WorkItem
from pipeline_breadcrumbs.testing import ArtifactRecorder, RecordCapture

METADATA_AUDIT: Final[Step] = Step(2, "Metadata Audit")
CLASSIFICATION: Final[Step] = Step(3, "Classification")
SCORE_SECTIONS: Final[Step] = Step(2, "Score Sections")
PAGE_EVIDENCE: Final[ArtifactKind] = ArtifactKind("page_evidence", "json", "application/json")


@final
class UnreachableArtifactSink(ArtifactSinkProtocol):
    """A sink whose destination is down: every `persist` raises the destination's own error."""

    @override
    async def persist(self, artifact: Artifact) -> None:
        raise ConnectionError("blob storage unreachable")


async def _run_a_step_that_fails_after(clock_testing: ClockTesting, pipeline_run: PipelineRun, work_item: WorkItem, elapsed_seconds: float) -> None:
    async with pipeline_run, pipeline_run.open_work_item(work_item) as work_item_scope, work_item_scope.step(METADATA_AUDIT):
        clock_testing.advance(elapsed_seconds)
        raise ValueError("bad json")


@pytest.mark.acceptance
class TestFailingStep:
    async def test_PipelineRun_WhenAStepRaises_ThenItLogsAFailedBreadcrumbAndTheExceptionEscapes(
        self, clock_testing: ClockTesting, artifact_recorder: ArtifactRecorder, run_logger: logging.Logger, record_capture: RecordCapture
    ) -> None:
        # Arrange
        work_item: WorkItem = create_random_work_item()
        expected_elapsed_seconds: float = 1.25
        pipeline_run: PipelineRun = PipelineRun(pipeline_name="demo", artifact_sink=artifact_recorder, logger=run_logger, clock=clock_testing.clock)

        # Act
        with pytest.raises(ValueError, match="bad json"):
            await _run_a_step_that_fails_after(clock_testing, pipeline_run, work_item, expected_elapsed_seconds)

        # Assert
        AsserterStepBoundaries.assert_exactly_these_step_boundaries(
            [ExpectedStepBoundary("2", "STARTED"), ExpectedStepBoundary("2", "FAILED", elapsed_seconds=expected_elapsed_seconds)],
            record_capture.records,
        )
        actual_failed_record: logging.LogRecord = record_capture.boundaries(EventKind.STEP)[-1]
        assert actual_failed_record.levelno == logging.WARNING
        assert RecordCapture.attribute(actual_failed_record, AttributeKey.FAILURE_TYPE) == "ValueError"
        assert RecordCapture.attribute(actual_failed_record, AttributeKey.FAILURE_MESSAGE) == "bad json"
        # The traceback is logged once, by the host's outer boundary; a step never repeats it.
        assert actual_failed_record.exc_info is None

    async def test_PipelineRun_WhenADiagnosticExceptionEscapesANestedStep_ThenTheInnermostStepIsStampedOntoItOnce(
        self, artifact_recorder: ArtifactRecorder, run_logger: logging.Logger
    ) -> None:
        # Arrange
        work_item: WorkItem = create_random_work_item()
        diagnostic_testing_error: DiagnosticTestingError = DiagnosticTestingError("response was not json")
        pipeline_run: PipelineRun = PipelineRun(pipeline_name="demo", artifact_sink=artifact_recorder, logger=run_logger)

        # Act
        with pytest.raises(DiagnosticTestingError):
            async with (
                pipeline_run,
                pipeline_run.open_work_item(work_item) as work_item_scope,
                work_item_scope.step(CLASSIFICATION) as parent_step_scope,
                parent_step_scope.step(SCORE_SECTIONS),
            ):
                raise diagnostic_testing_error

        # Assert - the child step stamps first; the parent finds the stamp and leaves it alone
        AsserterContextualData.assert_exactly_these_entries(
            {"FailedAtStepNumber": "3.2", "FailedAtStepName": "Score Sections", "FailedAtStepKey": "score_sections"},
            diagnostic_testing_error,
        )

    async def test_PipelineRun_WhenTheExceptionCarriesNoDiagnosticData_ThenItPassesThroughUntouched(
        self, artifact_recorder: ArtifactRecorder, run_logger: logging.Logger
    ) -> None:
        # Arrange
        work_item: WorkItem = create_random_work_item()
        pipeline_run: PipelineRun = PipelineRun(pipeline_name="demo", artifact_sink=artifact_recorder, logger=run_logger)

        # Act / Assert
        with pytest.raises(KeyError):
            async with pipeline_run, pipeline_run.open_work_item(work_item) as work_item_scope, work_item_scope.step(METADATA_AUDIT):
                raise KeyError("missing")


@pytest.mark.acceptance
class TestFailingSink:
    async def test_PipelineRun_WhenTheSinkFailsOnEmit_ThenAnArtifactSinkErrorNamesTheArtifactAndKeepsTheCause(
        self, run_logger: logging.Logger
    ) -> None:
        # Arrange
        work_item: WorkItem = create_random_work_item()
        expected_artifact_kind_key: str = PAGE_EVIDENCE.key
        pipeline_run: PipelineRun = PipelineRun(pipeline_name="demo", artifact_sink=UnreachableArtifactSink(), logger=run_logger)

        # Act
        with pytest.raises(ArtifactSinkError) as actual_raised:
            async with pipeline_run, pipeline_run.open_work_item(work_item) as work_item_scope, work_item_scope.step(METADATA_AUDIT) as step_scope:
                await step_scope.emit(PAGE_EVIDENCE, b"{}")

        # Assert
        assert isinstance(actual_raised.value.__cause__, ConnectionError)
        AsserterContextualData.assert_exactly_these_entries(
            {
                "ExceptionType": "ArtifactSinkError",
                "ArtifactKind": expected_artifact_kind_key,
                "ArtifactFilename": f"{work_item.stem}_step_02_{expected_artifact_kind_key}.json",
                "ArtifactBytes": 2,
                "FailedAtStepNumber": "2",
                "FailedAtStepName": "Metadata Audit",
                "FailedAtStepKey": "metadata_audit",
            },
            actual_raised.value,
        )

    async def test_PipelineRun_WhenTheManifestCannotBeWrittenWhileTheRunIsFailing_ThenTheOriginalFailureIsNotHidden(
        self, run_logger: logging.Logger
    ) -> None:
        # Arrange
        real_problem_message: str = "the real problem"
        pipeline_run: PipelineRun = PipelineRun(pipeline_name="demo", artifact_sink=UnreachableArtifactSink(), logger=run_logger)

        # Act / Assert - the run's own failure, not the storage outage, reaches the caller
        with pytest.raises(ValueError, match=real_problem_message):
            async with pipeline_run:
                raise ValueError(real_problem_message)

    async def test_PipelineRun_WhenTheManifestCannotBeWrittenAndNothingElseFailed_ThenTheOutageIsReported(self, run_logger: logging.Logger) -> None:
        # Arrange
        pipeline_run: PipelineRun = PipelineRun(pipeline_name="demo", artifact_sink=UnreachableArtifactSink(), logger=run_logger)

        # Act / Assert
        with pytest.raises(ArtifactSinkError):
            async with pipeline_run:
                pass


@pytest.mark.acceptance
class TestRunSummary:
    async def test_PipelineRun_WhenOneWorkItemFails_ThenTheRunSummaryCountsItAndIsLoggedAsAWarning(
        self, artifact_recorder: ArtifactRecorder, run_logger: logging.Logger, record_capture: RecordCapture
    ) -> None:
        # Arrange
        healthy_work_item: WorkItem = create_random_work_item()
        failing_work_item: WorkItem = create_random_work_item()
        pipeline_run: PipelineRun = PipelineRun(pipeline_name="demo", artifact_sink=artifact_recorder, logger=run_logger)

        # Act
        async with pipeline_run:
            async with pipeline_run.open_work_item(healthy_work_item) as work_item_scope, work_item_scope.step(METADATA_AUDIT):
                pass
            with pytest.raises(RuntimeError):
                async with pipeline_run.open_work_item(failing_work_item):
                    raise RuntimeError("boom")

        # Assert
        actual_run_summary_record: logging.LogRecord = record_capture.boundaries(EventKind.RUN)[-1]
        expected_outcome: str = "2 work item(s): 1 complete, 1 failed"
        assert RecordCapture.attribute(actual_run_summary_record, AttributeKey.OUTCOME) == expected_outcome
        assert RecordCapture.attribute(actual_run_summary_record, AttributeKey.STATUS) == "FAILED"
        assert actual_run_summary_record.levelno == logging.WARNING
