# Acceptance tests for the run manifest: the index a run writes last, so the first step whose
# output went wrong can be found without opening any other file. Observed through the artifact
# the run hands to its sink.

import asyncio
import logging
from typing import Final

import pytest
from breadcrumbs_acceptance_support.asserters.asserter_manifest import (
    AsserterManifest,
    ExpectedManifest,
    ExpectedManifestStep,
    ExpectedManifestWorkItem,
)
from breadcrumbs_acceptance_support.clock_testing import ClockTesting
from breadcrumbs_acceptance_support.data_generators import create_random_discriminator, create_random_pipeline_name, create_random_work_item
from breadcrumbs_acceptance_support.exceptions_testing import PlainTestingError

from pipeline_breadcrumbs import ArtifactKind, ArtifactRole, PipelineRun, Step, WorkItem, WorkItemScope
from pipeline_breadcrumbs.testing import ArtifactSinkTesting

LOAD_PAGES: Final[Step] = Step(1, "Load Pages")
LOAD_PAGES_STEP_PATH: Final[str] = str(LOAD_PAGES.step_number)
DETECT_SECTIONS: Final[Step] = Step(2, "Detect Sections")
PAGE_TEXT: Final[ArtifactKind] = ArtifactKind("page_text", "txt", "text/plain")
FINAL_REPORT: Final[ArtifactKind] = ArtifactKind("final_report", "md", "text/markdown", role=ArtifactRole.OUTPUT)


@pytest.mark.acceptance
class TestRunManifest:
    async def test_PipelineRun_WhenARunCompletes_ThenTheManifestIsTheLastArtifactAndIndexesTheRun(
        self, clock_testing: ClockTesting, artifact_sink_testing: ArtifactSinkTesting, run_logger: logging.Logger
    ) -> None:
        # Arrange
        work_item: WorkItem = create_random_work_item()
        pipeline_name: str = create_random_pipeline_name()
        expected_step_outcome: str = "Loaded 1 page"
        discriminator: str = create_random_discriminator()
        pipeline_run: PipelineRun = PipelineRun(
            pipeline_name=pipeline_name, sink=artifact_sink_testing, logger=run_logger, supplied_clock=clock_testing.clock
        )
        expected_manifest: ExpectedManifest = ExpectedManifest(
            pipeline_name=pipeline_name,
            run_id=pipeline_run.run_id,
            run_status="COMPLETE",
            elapsed_seconds=4.0,
            manifest_work_items=[
                ExpectedManifestWorkItem(
                    name=work_item.name,
                    work_item_status="COMPLETE",
                    manifest_steps=[
                        ExpectedManifestStep(LOAD_PAGES_STEP_PATH, "COMPLETE", elapsed_seconds=1.5, outcome=expected_step_outcome),
                        ExpectedManifestStep("2", "COMPLETE", elapsed_seconds=2.0),
                    ],
                    artifact_filenames=[f"{work_item.stem}_step_01_page_text_{discriminator}.txt"],
                )
            ],
        )

        # Act
        async with pipeline_run:
            async with pipeline_run.open_work_item(work_item) as work_item_scope:
                async with work_item_scope.step(LOAD_PAGES) as step_scope:
                    clock_testing.advance(1.5)
                    await step_scope.emit(PAGE_TEXT, b"hello", discriminator=discriminator)
                    step_scope.outcome(expected_step_outcome)
                async with work_item_scope.step(DETECT_SECTIONS):
                    clock_testing.advance(2.0)
            clock_testing.advance(0.5)

        # Assert - the asserter also checks that the last artifact is the manifest itself
        AsserterManifest.assert_manifest(expected_manifest, artifact_sink_testing.artifacts[-1])

    async def test_PipelineRun_WhenAStepEmitsAnOutputArtifact_ThenTheManifestMarksItAsAnOutput(
        self, clock_testing: ClockTesting, artifact_sink_testing: ArtifactSinkTesting, run_logger: logging.Logger
    ) -> None:
        # Arrange
        work_item: WorkItem = create_random_work_item()
        pipeline_name: str = create_random_pipeline_name()
        pipeline_run: PipelineRun = PipelineRun(
            pipeline_name=pipeline_name, sink=artifact_sink_testing, logger=run_logger, supplied_clock=clock_testing.clock
        )
        expected_report_filename: str = f"{work_item.stem}_step_01_final_report.md"
        expected_manifest: ExpectedManifest = ExpectedManifest(
            pipeline_name=pipeline_name,
            run_id=pipeline_run.run_id,
            run_status="COMPLETE",
            elapsed_seconds=0.0,
            manifest_work_items=[
                ExpectedManifestWorkItem(
                    name=work_item.name,
                    work_item_status="COMPLETE",
                    manifest_steps=[ExpectedManifestStep(LOAD_PAGES_STEP_PATH, "COMPLETE")],
                    artifact_filenames=[expected_report_filename],
                    artifact_role_by_filename={expected_report_filename: ArtifactRole.OUTPUT.value},
                )
            ],
        )

        # Act
        async with pipeline_run, pipeline_run.open_work_item(work_item) as work_item_scope, work_item_scope.step(LOAD_PAGES) as step_scope:
            await step_scope.emit(FINAL_REPORT, b"# Report")

        # Assert
        AsserterManifest.assert_manifest(expected_manifest, artifact_sink_testing.artifacts[-1])

    async def test_PipelineRun_WhenOneWorkItemFails_ThenTheManifestMarksTheRunFailedAndRecordsWhy(
        self, clock_testing: ClockTesting, artifact_sink_testing: ArtifactSinkTesting, run_logger: logging.Logger
    ) -> None:
        # Arrange
        failing_work_item: WorkItem = create_random_work_item()
        healthy_work_item: WorkItem = create_random_work_item()
        failure_message: str = "unreadable"
        expected_failure: str = f"PlainTestingError: {failure_message}"
        pipeline_name: str = create_random_pipeline_name()
        pipeline_run: PipelineRun = PipelineRun(
            pipeline_name=pipeline_name, sink=artifact_sink_testing, logger=run_logger, supplied_clock=clock_testing.clock
        )
        expected_manifest: ExpectedManifest = ExpectedManifest(
            pipeline_name=pipeline_name,
            run_id=pipeline_run.run_id,
            run_status="FAILED",
            elapsed_seconds=0.0,
            manifest_work_items=[
                ExpectedManifestWorkItem(
                    name=failing_work_item.name,
                    work_item_status="FAILED",
                    failure=expected_failure,
                    manifest_steps=[ExpectedManifestStep(LOAD_PAGES_STEP_PATH, "FAILED", failure=expected_failure)],
                ),
                ExpectedManifestWorkItem(
                    name=healthy_work_item.name,
                    work_item_status="COMPLETE",
                    manifest_steps=[ExpectedManifestStep(LOAD_PAGES_STEP_PATH, "COMPLETE")],
                ),
            ],
        )

        # Act
        async with pipeline_run:
            with pytest.raises(PlainTestingError, match=failure_message):
                async with pipeline_run.open_work_item(failing_work_item) as work_item_scope, work_item_scope.step(LOAD_PAGES):
                    raise PlainTestingError(failure_message)
            async with pipeline_run.open_work_item(healthy_work_item) as work_item_scope, work_item_scope.step(LOAD_PAGES):
                pass

        # Assert
        AsserterManifest.assert_manifest(expected_manifest, artifact_sink_testing.artifacts[-1])

    async def test_PipelineRun_WhenAChildStepIsSkipped_ThenTheManifestListsItWithItsReason(
        self, clock_testing: ClockTesting, artifact_sink_testing: ArtifactSinkTesting, run_logger: logging.Logger
    ) -> None:
        # Arrange
        work_item: WorkItem = create_random_work_item()
        skip_reason: str = "nothing to reconcile"
        pipeline_name: str = create_random_pipeline_name()
        pipeline_run: PipelineRun = PipelineRun(
            pipeline_name=pipeline_name, sink=artifact_sink_testing, logger=run_logger, supplied_clock=clock_testing.clock
        )
        expected_manifest: ExpectedManifest = ExpectedManifest(
            pipeline_name=pipeline_name,
            run_id=pipeline_run.run_id,
            run_status="COMPLETE",
            elapsed_seconds=0.0,
            manifest_work_items=[
                ExpectedManifestWorkItem(
                    name=work_item.name,
                    work_item_status="COMPLETE",
                    manifest_steps=[
                        ExpectedManifestStep(LOAD_PAGES_STEP_PATH, "COMPLETE"),
                        ExpectedManifestStep("1.2", "SKIPPED", outcome=skip_reason),
                    ],
                )
            ],
        )

        # Act
        async with pipeline_run, pipeline_run.open_work_item(work_item) as work_item_scope, work_item_scope.step(LOAD_PAGES) as step_scope:
            step_scope.skipped(DETECT_SECTIONS, skip_reason)

        # Assert
        AsserterManifest.assert_manifest(expected_manifest, artifact_sink_testing.artifacts[-1])

    async def test_PipelineRun_WhenTheSameWorkItemIsOpenedAgainAfterAFailure_ThenBothAttemptsStayInTheManifestAndTheRunIsFailed(
        self, clock_testing: ClockTesting, artifact_sink_testing: ArtifactSinkTesting, run_logger: logging.Logger
    ) -> None:
        # Arrange - a retry reopens the same work item; the failure of the first attempt must not be erased by the success of the second
        work_item: WorkItem = create_random_work_item()
        first_attempt_failure_message: str = "first attempt"
        expected_first_attempt_failure: str = f"PlainTestingError: {first_attempt_failure_message}"
        pipeline_name: str = create_random_pipeline_name()
        pipeline_run: PipelineRun = PipelineRun(
            pipeline_name=pipeline_name, sink=artifact_sink_testing, logger=run_logger, supplied_clock=clock_testing.clock
        )
        expected_manifest: ExpectedManifest = ExpectedManifest(
            pipeline_name=pipeline_name,
            run_id=pipeline_run.run_id,
            run_status="FAILED",
            elapsed_seconds=0.0,
            manifest_work_items=[
                ExpectedManifestWorkItem(
                    name=work_item.name,
                    work_item_status="FAILED",
                    failure=expected_first_attempt_failure,
                    manifest_steps=[ExpectedManifestStep(LOAD_PAGES_STEP_PATH, "FAILED", failure=expected_first_attempt_failure)],
                ),
                ExpectedManifestWorkItem(
                    name=work_item.name,
                    work_item_status="COMPLETE",
                    manifest_steps=[ExpectedManifestStep(LOAD_PAGES_STEP_PATH, "COMPLETE")],
                ),
            ],
        )

        # Act
        async with pipeline_run:
            with pytest.raises(PlainTestingError, match=first_attempt_failure_message):
                async with pipeline_run.open_work_item(work_item) as work_item_scope, work_item_scope.step(LOAD_PAGES):
                    raise PlainTestingError(first_attempt_failure_message)
            async with pipeline_run.open_work_item(work_item) as work_item_scope, work_item_scope.step(LOAD_PAGES):
                pass

        # Assert
        AsserterManifest.assert_manifest(expected_manifest, artifact_sink_testing.artifacts[-1])

    async def test_PipelineRun_WhenTheSameStepIsOpenedOncePerPage_ThenTheManifestKeepsEveryOpening(
        self, clock_testing: ClockTesting, artifact_sink_testing: ArtifactSinkTesting, run_logger: logging.Logger
    ) -> None:
        # Arrange
        work_item: WorkItem = create_random_work_item()
        page_failure_message: str = "page 1 is unreadable"
        expected_page_failure: str = f"PlainTestingError: {page_failure_message}"
        pipeline_name: str = create_random_pipeline_name()
        pipeline_run: PipelineRun = PipelineRun(
            pipeline_name=pipeline_name, sink=artifact_sink_testing, logger=run_logger, supplied_clock=clock_testing.clock
        )
        expected_manifest: ExpectedManifest = ExpectedManifest(
            pipeline_name=pipeline_name,
            run_id=pipeline_run.run_id,
            run_status="FAILED",
            elapsed_seconds=0.0,
            manifest_work_items=[
                ExpectedManifestWorkItem(
                    name=work_item.name,
                    work_item_status="FAILED",
                    failure=expected_page_failure,
                    manifest_steps=[
                        ExpectedManifestStep(LOAD_PAGES_STEP_PATH, "COMPLETE"),
                        ExpectedManifestStep(LOAD_PAGES_STEP_PATH, "FAILED", failure=expected_page_failure),
                    ],
                )
            ],
        )

        async def open_the_step_once_per_page(work_item_scope: WorkItemScope) -> None:
            for page_number in range(3):
                async with work_item_scope.step(LOAD_PAGES):
                    if page_number == 1:
                        raise PlainTestingError(page_failure_message)

        # Act - the second page fails, so the work item ends before a third opening
        async with pipeline_run:
            with pytest.raises(PlainTestingError, match=page_failure_message):
                async with pipeline_run.open_work_item(work_item) as work_item_scope:
                    await open_the_step_once_per_page(work_item_scope)

        # Assert
        AsserterManifest.assert_manifest(expected_manifest, artifact_sink_testing.artifacts[-1])

    async def test_PipelineRun_WhenTheSameStepRunsOnSeveralPagesAtOnce_ThenEachOpeningClosesItsOwnRecord(
        self, clock_testing: ClockTesting, artifact_sink_testing: ArtifactSinkTesting, run_logger: logging.Logger
    ) -> None:
        # Arrange
        work_item: WorkItem = create_random_work_item()
        pipeline_name: str = create_random_pipeline_name()
        pipeline_run: PipelineRun = PipelineRun(
            pipeline_name=pipeline_name, sink=artifact_sink_testing, logger=run_logger, supplied_clock=clock_testing.clock
        )
        expected_manifest: ExpectedManifest = ExpectedManifest(
            pipeline_name=pipeline_name,
            run_id=pipeline_run.run_id,
            run_status="COMPLETE",
            elapsed_seconds=0.0,
            manifest_work_items=[
                ExpectedManifestWorkItem(
                    name=work_item.name,
                    work_item_status="COMPLETE",
                    manifest_steps=[
                        ExpectedManifestStep(LOAD_PAGES_STEP_PATH, "COMPLETE", outcome=f"page {page_number}") for page_number in range(3)
                    ],
                )
            ],
        )

        async def load_one_page(work_item_scope: WorkItemScope, page_number: int) -> None:
            async with work_item_scope.step(LOAD_PAGES) as step_scope:
                # Yield to the event loop so the other openings start before this one closes; without it they would run one after another.
                await asyncio.sleep(0)
                step_scope.outcome(f"page {page_number}")

        # Act - three scopes at the same step path run concurrently, the way a per-page fan-out does
        async with pipeline_run, pipeline_run.open_work_item(work_item) as work_item_scope:
            await asyncio.gather(*(load_one_page(work_item_scope, page_number) for page_number in range(3)))

        # Assert
        AsserterManifest.assert_manifest(expected_manifest, artifact_sink_testing.artifacts[-1])
