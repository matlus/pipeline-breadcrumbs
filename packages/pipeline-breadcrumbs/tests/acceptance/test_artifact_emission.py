# Acceptance tests for emitting artifacts: a step hands over bytes and a declared kind, and the
# artifact derives its own name. Observed through the artifacts a recording sink received and the
# progress line the emit wrote.

import logging
from typing import Final

import pytest
from breadcrumbs_acceptance_support.asserters.asserter_artifacts import AsserterArtifacts
from breadcrumbs_acceptance_support.data_generators import create_random_work_item

from pipeline_breadcrumbs import ArtifactKind, ArtifactRole, AttributeKey, PipelineRun, Step, StepArtifact, WorkItem
from pipeline_breadcrumbs.testing import ArtifactRecorder, RecordCapture

METADATA_AUDIT: Final[Step] = Step(2, "Metadata Audit")
PAGE_EVIDENCE: Final[ArtifactKind] = ArtifactKind("page_evidence", "json", "application/json")


@pytest.mark.acceptance
class TestEmit:
    async def test_StepScope_WhenAnArtifactIsEmitted_ThenTheSinkReceivesItAndTheEmitIsLogged(
        self, artifact_recorder: ArtifactRecorder, run_logger: logging.Logger, record_capture: RecordCapture
    ) -> None:
        # Arrange
        work_item: WorkItem = create_random_work_item()
        expected_content: bytes = b'{"ok": true}'
        pipeline_run: PipelineRun = PipelineRun(pipeline_name="demo", sink=artifact_recorder, logger=run_logger)

        # Act
        async with pipeline_run, pipeline_run.open_work_item(work_item) as work_item_scope, work_item_scope.step(METADATA_AUDIT) as step_scope:
            actual_emitted_artifact: StepArtifact = await step_scope.emit(PAGE_EVIDENCE, expected_content, discriminator="page_0003")

        # Assert
        expected_filename: str = f"{work_item.stem}_step_02_page_evidence_page_0003.json"
        assert actual_emitted_artifact.filename == expected_filename
        assert artifact_recorder.of_kind(PAGE_EVIDENCE)[0].content == expected_content
        actual_emit_record: logging.LogRecord = next(
            actual_log_record for actual_log_record in record_capture.records if AttributeKey.ARTIFACT_FILENAME in actual_log_record.__dict__
        )
        assert actual_emit_record.getMessage() == f"Emitted artifact: {expected_filename} (12 B)"
        assert RecordCapture.attribute(actual_emit_record, AttributeKey.ARTIFACT_BYTES) == 12

    async def test_StepScope_WhenAnArtifactIsEmitted_ThenItDescribesItselfToTheSink(
        self, artifact_recorder: ArtifactRecorder, run_logger: logging.Logger
    ) -> None:
        # Arrange
        work_item: WorkItem = create_random_work_item()
        pipeline_run: PipelineRun = PipelineRun(pipeline_name="demo", sink=artifact_recorder, logger=run_logger)

        # Act
        async with pipeline_run, pipeline_run.open_work_item(work_item) as work_item_scope, work_item_scope.step(METADATA_AUDIT) as step_scope:
            await step_scope.emit(PAGE_EVIDENCE, b"{}")

        # Assert - the sink can persist it blindly: what it holds, its media type and its bytes travel with it
        actual_step_artifact: StepArtifact = next(
            actual_recorded for actual_recorded in artifact_recorder.artifacts if isinstance(actual_recorded, StepArtifact)
        )
        assert (actual_step_artifact.artifact_type, actual_step_artifact.content_type, actual_step_artifact.content) == (
            "page_evidence",
            "application/json",
            b"{}",
        )

    async def test_StepScope_WhenStepsEmitPastStepNine_ThenADirectoryListingSortsInPipelineOrder(
        self, artifact_recorder: ArtifactRecorder, run_logger: logging.Logger
    ) -> None:
        # Arrange
        work_item: WorkItem = create_random_work_item()
        pipeline_run: PipelineRun = PipelineRun(pipeline_name="demo", sink=artifact_recorder, logger=run_logger)

        # Act - steps are declared out of order on purpose
        async with pipeline_run, pipeline_run.open_work_item(work_item) as work_item_scope:
            for step_number in (10, 2, 1, 9, 11):
                async with work_item_scope.step(Step(step_number, f"Step {step_number}")) as step_scope:
                    await step_scope.emit(PAGE_EVIDENCE, b"")

        # Assert
        actual_filenames_sorted_as_a_listing: list[str] = sorted(
            actual_artifact.filename for actual_artifact in artifact_recorder.artifacts if isinstance(actual_artifact, StepArtifact)
        )
        expected_filenames_in_pipeline_order: list[str] = [
            f"{work_item.stem}_step_{step_number:02d}_page_evidence.json" for step_number in (1, 2, 9, 10, 11)
        ]
        assert actual_filenames_sorted_as_a_listing == expected_filenames_in_pipeline_order

    @pytest.mark.parametrize("unsafe_discriminator", ["a/b", "page 3", "..\\x", ""])
    async def test_StepScope_WhenTheDiscriminatorIsUnsafeForAFilename_ThenTheEmitIsRefused(
        self, unsafe_discriminator: str, artifact_recorder: ArtifactRecorder, run_logger: logging.Logger
    ) -> None:
        # Arrange
        work_item: WorkItem = create_random_work_item()
        pipeline_run: PipelineRun = PipelineRun(pipeline_name="demo", sink=artifact_recorder, logger=run_logger)

        # Act / Assert
        with pytest.raises(ValueError, match="discriminator"):
            async with pipeline_run, pipeline_run.open_work_item(work_item) as work_item_scope, work_item_scope.step(METADATA_AUDIT) as step_scope:
                await step_scope.emit(PAGE_EVIDENCE, b"{}", discriminator=unsafe_discriminator)


@pytest.mark.acceptance
class TestArtifactKindDeclaration:
    @pytest.mark.parametrize("vague_key", ["result", "output", "data", "artifact", "payload", "results"])
    def test_ArtifactKind_WhenTheKeyIsVague_ThenItIsRefused(self, vague_key: str) -> None:
        # Arrange / Act / Assert - a kind named for its role can be found again; "result" cannot
        with pytest.raises(ValueError, match="too vague"):
            ArtifactKind(vague_key, "json", "application/json")

    @pytest.mark.parametrize("malformed_key", ["Page Evidence", "page-evidence", "_page", "page__evidence"])
    def test_ArtifactKind_WhenTheKeyIsMalformed_ThenItIsRefused(self, malformed_key: str) -> None:
        # Arrange / Act / Assert
        with pytest.raises(ValueError, match="lowercase words"):
            ArtifactKind(malformed_key, "json", "application/json")

    def test_ArtifactKind_WhenTheExtensionCarriesADot_ThenItIsRefused(self) -> None:
        # Arrange / Act / Assert
        with pytest.raises(ValueError, match="without a dot"):
            ArtifactKind("page_evidence", ".json", "application/json")

    def test_ArtifactKind_WhenNoRoleIsGiven_ThenTheArtifactIsInterim(self) -> None:
        # Arrange / Act
        actual_artifact_kind: ArtifactKind = ArtifactKind("page_evidence", "json", "application/json")

        # Assert
        assert actual_artifact_kind.role is ArtifactRole.INTERIM


@pytest.mark.acceptance
class TestWorkItemIdentity:
    def test_WorkItem_WhenTheNameHasAnExtension_ThenTheStemDropsIt(self) -> None:
        # Arrange / Act
        actual_work_item: WorkItem = WorkItem("7f3c", "Contract 12.pdf")

        # Assert
        assert actual_work_item.stem == "Contract 12"

    def test_WorkItem_WhenTheNameHasNoExtension_ThenTheStemIsTheName(self) -> None:
        # Arrange / Act / Assert
        assert WorkItem("1", "request-8841").stem == "request-8841"

    def test_WorkItem_WhenTheIdentityIsBlank_ThenItIsRefused(self) -> None:
        # Arrange / Act / Assert
        with pytest.raises(ValueError, match="id must not be blank"):
            WorkItem(" ", "x")
        with pytest.raises(ValueError, match="name must not be blank"):
            WorkItem("1", " ")


@pytest.mark.acceptance
class TestRunLevelArtifact:
    async def test_PipelineRun_WhenTheRunCloses_ThenTheManifestHasNoWorkItemPrefix(
        self, artifact_recorder: ArtifactRecorder, run_logger: logging.Logger
    ) -> None:
        # Arrange
        pipeline_run: PipelineRun = PipelineRun(pipeline_name="demo", sink=artifact_recorder, logger=run_logger)

        # Act
        async with pipeline_run:
            pass

        # Assert
        AsserterArtifacts.assert_exactly_these_filenames_in_order(["manifest.json"], artifact_recorder.artifacts)
