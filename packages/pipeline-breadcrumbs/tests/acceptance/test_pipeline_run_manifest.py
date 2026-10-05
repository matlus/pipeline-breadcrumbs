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
from breadcrumbs_acceptance_support.data_generators import create_random_work_item

from pipeline_breadcrumbs import MANIFEST_KIND, Artifact, ArtifactKind, ArtifactRole, PipelineRun, Step, WorkItem, WorkItemScope
from pipeline_breadcrumbs.testing import ArtifactRecorder

LOAD_PAGES: Final[Step] = Step(1, "Load Pages")
DETECT_SECTIONS: Final[Step] = Step(2, "Detect Sections")
PAGE_TEXT: Final[ArtifactKind] = ArtifactKind("page_text", "txt", "text/plain")
FINAL_REPORT: Final[ArtifactKind] = ArtifactKind("final_report", "md", "text/markdown", role=ArtifactRole.OUTPUT)


@pytest.mark.acceptance
class TestRunManifest:
    async def test_PipelineRun_WhenARunCompletes_ThenTheManifestIsTheLastArtifactAndIndexesTheRun(
        self, clock_testing: ClockTesting, artifact_recorder: ArtifactRecorder, run_logger: logging.Logger
    ) -> None:
        # Arrange
        work_item: WorkItem = create_random_work_item()
        pipeline_name: str = "demo"
        pipeline_run: PipelineRun = PipelineRun(
            pipeline_name=pipeline_name, artifact_sink=artifact_recorder, logger=run_logger, clock=clock_testing.clock
        )
        expected_manifest: ExpectedManifest = ExpectedManifest(
            pipeline_name=pipeline_name,
            run_id=pipeline_run.run_id,
            run_status="COMPLETE",
            elapsed_seconds=4.0,
            work_item_records=[
                ExpectedManifestWorkItem(
                    name=work_item.name,
                    work_item_status="COMPLETE",
                    step_records=[
                        ExpectedManifestStep("1", "COMPLETE", elapsed_seconds=1.5, outcome="Loaded 1 page"),
                        ExpectedManifestStep("2", "COMPLETE", elapsed_seconds=2.0),
                    ],
                    artifact_filenames=[f"{work_item.stem}_step_01_page_text_page_0000.txt"],
                )
            ],
        )

        # Act
        async with pipeline_run:
            async with pipeline_run.open_work_item(work_item) as work_item_scope:
                async with work_item_scope.step(LOAD_PAGES) as step_scope:
                    clock_testing.advance(1.5)
                    await step_scope.emit(PAGE_TEXT, b"hello", discriminator="page_0000")
                    step_scope.outcome("Loaded 1 page")
                async with work_item_scope.step(DETECT_SECTIONS):
                    clock_testing.advance(2.0)
            clock_testing.advance(0.5)

        # Assert
        actual_last_artifact: Artifact = artifact_recorder.artifacts[-1]
        assert actual_last_artifact.artifact_kind == MANIFEST_KIND
        AsserterManifest.assert_manifest(expected_manifest, actual_last_artifact)

    async def test_PipelineRun_WhenAStepEmitsAnOutputArtifact_ThenTheManifestMarksItAsAnOutput(
        self, artifact_recorder: ArtifactRecorder, run_logger: logging.Logger
    ) -> None:
        # Arrange
        work_item: WorkItem = create_random_work_item()
        pipeline_run: PipelineRun = PipelineRun(pipeline_name="demo", artifact_sink=artifact_recorder, logger=run_logger)

        # Act
        async with pipeline_run, pipeline_run.open_work_item(work_item) as work_item_scope, work_item_scope.step(LOAD_PAGES) as step_scope:
            await step_scope.emit(FINAL_REPORT, b"# Report")

        # Assert
        actual_output_roles: list[ArtifactRole] = [
            actual_artifact.artifact_kind.role for actual_artifact in artifact_recorder.artifacts if actual_artifact.artifact_kind == FINAL_REPORT
        ]
        assert actual_output_roles == [ArtifactRole.OUTPUT]
        assert b'"role": "output"' in artifact_recorder.artifacts[-1].content

    async def test_PipelineRun_WhenOneWorkItemFails_ThenTheManifestMarksTheRunFailedAndRecordsWhy(
        self, clock_testing: ClockTesting, artifact_recorder: ArtifactRecorder, run_logger: logging.Logger
    ) -> None:
        # Arrange
        failing_work_item: WorkItem = create_random_work_item()
        healthy_work_item: WorkItem = create_random_work_item()
        pipeline_name: str = "demo"
        pipeline_run: PipelineRun = PipelineRun(
            pipeline_name=pipeline_name, artifact_sink=artifact_recorder, logger=run_logger, clock=clock_testing.clock
        )
        expected_manifest: ExpectedManifest = ExpectedManifest(
            pipeline_name=pipeline_name,
            run_id=pipeline_run.run_id,
            run_status="FAILED",
            elapsed_seconds=0.0,
            work_item_records=[
                ExpectedManifestWorkItem(
                    name=failing_work_item.name,
                    work_item_status="FAILED",
                    failure="ValueError: unreadable",
                    step_records=[ExpectedManifestStep("1", "FAILED", failure="ValueError: unreadable")],
                ),
                ExpectedManifestWorkItem(
                    name=healthy_work_item.name,
                    work_item_status="COMPLETE",
                    step_records=[ExpectedManifestStep("1", "COMPLETE")],
                ),
            ],
        )

        # Act
        async with pipeline_run:
            with pytest.raises(ValueError, match="unreadable"):
                async with pipeline_run.open_work_item(failing_work_item) as work_item_scope, work_item_scope.step(LOAD_PAGES):
                    raise ValueError("unreadable")
            async with pipeline_run.open_work_item(healthy_work_item) as work_item_scope, work_item_scope.step(LOAD_PAGES):
                pass

        # Assert
        AsserterManifest.assert_manifest(expected_manifest, artifact_recorder.artifacts[-1])

    async def test_PipelineRun_WhenAChildStepIsSkipped_ThenTheManifestListsItWithItsReason(
        self, clock_testing: ClockTesting, artifact_recorder: ArtifactRecorder, run_logger: logging.Logger
    ) -> None:
        # Arrange
        work_item: WorkItem = create_random_work_item()
        pipeline_name: str = "demo"
        pipeline_run: PipelineRun = PipelineRun(
            pipeline_name=pipeline_name, artifact_sink=artifact_recorder, logger=run_logger, clock=clock_testing.clock
        )
        expected_manifest: ExpectedManifest = ExpectedManifest(
            pipeline_name=pipeline_name,
            run_id=pipeline_run.run_id,
            run_status="COMPLETE",
            elapsed_seconds=0.0,
            work_item_records=[
                ExpectedManifestWorkItem(
                    name=work_item.name,
                    work_item_status="COMPLETE",
                    step_records=[
                        ExpectedManifestStep("1", "COMPLETE"),
                        ExpectedManifestStep("1.2", "SKIPPED", outcome="nothing to reconcile"),
                    ],
                )
            ],
        )

        # Act
        async with pipeline_run, pipeline_run.open_work_item(work_item) as work_item_scope, work_item_scope.step(LOAD_PAGES) as step_scope:
            step_scope.skipped(DETECT_SECTIONS, "nothing to reconcile")

        # Assert
        AsserterManifest.assert_manifest(expected_manifest, artifact_recorder.artifacts[-1])

    async def test_PipelineRun_WhenTheSameWorkItemIsOpenedAgainAfterAFailure_ThenBothAttemptsStayInTheManifestAndTheRunIsFailed(
        self, clock_testing: ClockTesting, artifact_recorder: ArtifactRecorder, run_logger: logging.Logger
    ) -> None:
        # Arrange - a retry reopens the same work item; the failure of the first attempt must not be erased by the success of the second
        work_item: WorkItem = create_random_work_item()
        pipeline_name: str = "demo"
        pipeline_run: PipelineRun = PipelineRun(
            pipeline_name=pipeline_name, artifact_sink=artifact_recorder, logger=run_logger, clock=clock_testing.clock
        )
        expected_manifest: ExpectedManifest = ExpectedManifest(
            pipeline_name=pipeline_name,
            run_id=pipeline_run.run_id,
            run_status="FAILED",
            elapsed_seconds=0.0,
            work_item_records=[
                ExpectedManifestWorkItem(
                    name=work_item.name,
                    work_item_status="FAILED",
                    failure="ValueError: first attempt",
                    step_records=[ExpectedManifestStep("1", "FAILED", failure="ValueError: first attempt")],
                ),
                ExpectedManifestWorkItem(
                    name=work_item.name,
                    work_item_status="COMPLETE",
                    step_records=[ExpectedManifestStep("1", "COMPLETE")],
                ),
            ],
        )

        # Act
        async with pipeline_run:
            with pytest.raises(ValueError, match="first attempt"):
                async with pipeline_run.open_work_item(work_item) as work_item_scope, work_item_scope.step(LOAD_PAGES):
                    raise ValueError("first attempt")
            async with pipeline_run.open_work_item(work_item) as work_item_scope, work_item_scope.step(LOAD_PAGES):
                pass

        # Assert
        AsserterManifest.assert_manifest(expected_manifest, artifact_recorder.artifacts[-1])

    async def test_PipelineRun_WhenTheSameStepIsOpenedOncePerPage_ThenTheManifestKeepsEveryOpening(
        self, clock_testing: ClockTesting, artifact_recorder: ArtifactRecorder, run_logger: logging.Logger
    ) -> None:
        # Arrange
        work_item: WorkItem = create_random_work_item()
        pipeline_name: str = "demo"
        pipeline_run: PipelineRun = PipelineRun(
            pipeline_name=pipeline_name, artifact_sink=artifact_recorder, logger=run_logger, clock=clock_testing.clock
        )
        expected_manifest: ExpectedManifest = ExpectedManifest(
            pipeline_name=pipeline_name,
            run_id=pipeline_run.run_id,
            run_status="FAILED",
            elapsed_seconds=0.0,
            work_item_records=[
                ExpectedManifestWorkItem(
                    name=work_item.name,
                    work_item_status="FAILED",
                    failure="ValueError: page 1 is unreadable",
                    step_records=[
                        ExpectedManifestStep("1", "COMPLETE"),
                        ExpectedManifestStep("1", "FAILED", failure="ValueError: page 1 is unreadable"),
                    ],
                )
            ],
        )

        async def open_the_step_once_per_page(work_item_scope: WorkItemScope) -> None:
            for page_number in range(3):
                async with work_item_scope.step(LOAD_PAGES):
                    if page_number == 1:
                        raise ValueError("page 1 is unreadable")

        # Act - the second page fails, so the work item ends before a third opening
        async with pipeline_run:
            with pytest.raises(ValueError, match="page 1 is unreadable"):
                async with pipeline_run.open_work_item(work_item) as work_item_scope:
                    await open_the_step_once_per_page(work_item_scope)

        # Assert
        AsserterManifest.assert_manifest(expected_manifest, artifact_recorder.artifacts[-1])

    async def test_PipelineRun_WhenTheSameStepRunsOnSeveralPagesAtOnce_ThenEachOpeningClosesItsOwnRecord(
        self, clock_testing: ClockTesting, artifact_recorder: ArtifactRecorder, run_logger: logging.Logger
    ) -> None:
        # Arrange
        work_item: WorkItem = create_random_work_item()
        pipeline_name: str = "demo"
        pipeline_run: PipelineRun = PipelineRun(
            pipeline_name=pipeline_name, artifact_sink=artifact_recorder, logger=run_logger, clock=clock_testing.clock
        )
        expected_manifest: ExpectedManifest = ExpectedManifest(
            pipeline_name=pipeline_name,
            run_id=pipeline_run.run_id,
            run_status="COMPLETE",
            elapsed_seconds=0.0,
            work_item_records=[
                ExpectedManifestWorkItem(
                    name=work_item.name,
                    work_item_status="COMPLETE",
                    step_records=[ExpectedManifestStep("1", "COMPLETE", outcome=f"page {page_number}") for page_number in range(3)],
                )
            ],
        )

        async def load_one_page(work_item_scope: WorkItemScope, page_number: int) -> None:
            async with work_item_scope.step(LOAD_PAGES) as step_scope:
                await asyncio.sleep(0)
                step_scope.outcome(f"page {page_number}")

        # Act - three scopes at the same step path run concurrently, the way a per-page fan-out does
        async with pipeline_run, pipeline_run.open_work_item(work_item) as work_item_scope:
            await asyncio.gather(*(load_one_page(work_item_scope, page_number) for page_number in range(3)))

        # Assert
        AsserterManifest.assert_manifest(expected_manifest, artifact_recorder.artifacts[-1])
