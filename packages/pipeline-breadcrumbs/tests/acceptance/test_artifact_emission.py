# Acceptance tests for emitting artifacts: a step hands over bytes and a declared kind, and the
# artifact derives its own name. Observed through the artifacts a recording sink received and the
# progress line the emit wrote.

import logging
import secrets
from typing import Final

import pytest
from breadcrumbs_acceptance_support.asserters.asserter_artifacts import AsserterArtifacts
from breadcrumbs_acceptance_support.asserters.asserter_exception import AsserterException, ExpectedException
from breadcrumbs_acceptance_support.asserters.asserter_log_record import AsserterLogRecord, ExpectedLogRecord
from breadcrumbs_acceptance_support.data_generators import create_random_work_item

from pipeline_breadcrumbs import ArtifactKind, ArtifactRole, AttributeKey, InvalidDeclarationError, PipelineRun, Step, StepArtifact, WorkItem
from pipeline_breadcrumbs.testing import ArtifactSinkTesting, RecordCapture

PIPELINE_NAME: Final[str] = "demo"
MANIFEST_FILENAME: Final[str] = "manifest.json"
METADATA_AUDIT: Final[Step] = Step(2, "Metadata Audit")
PAGE_EVIDENCE: Final[ArtifactKind] = ArtifactKind("page_evidence", "json", "application/json")
_RANDOM_SUFFIX_BYTES: Final[int] = 4


def create_random_document_stem() -> str:
    return f"Document {secrets.token_hex(_RANDOM_SUFFIX_BYTES)}"


@pytest.mark.acceptance
class TestEmit:
    async def test_StepScope_WhenAnArtifactIsEmitted_ThenTheSinkReceivesItAndTheEmitIsLogged(
        self, artifact_sink_testing: ArtifactSinkTesting, run_logger: logging.Logger, record_capture: RecordCapture
    ) -> None:
        # Arrange
        work_item: WorkItem = create_random_work_item()
        expected_content: bytes = b'{"ok": true}'
        discriminator: str = "page_0003"
        pipeline_run: PipelineRun = PipelineRun(pipeline_name=PIPELINE_NAME, sink=artifact_sink_testing, logger=run_logger)
        expected_filename: str = f"{work_item.stem}_step_02_page_evidence_{discriminator}.json"
        expected_emit_record: ExpectedLogRecord = ExpectedLogRecord(
            message=f"Emitted artifact: {expected_filename} (12 B)",
            attribute_value_by_key={AttributeKey.ARTIFACT_FILENAME: expected_filename, AttributeKey.ARTIFACT_BYTES: len(expected_content)},
        )

        # Act
        async with pipeline_run, pipeline_run.open_work_item(work_item) as work_item_scope, work_item_scope.step(METADATA_AUDIT) as step_scope:
            actual_emitted_step_artifact: StepArtifact = await step_scope.emit(PAGE_EVIDENCE, expected_content, discriminator=discriminator)

        # Assert
        assert actual_emitted_step_artifact.filename == expected_filename
        assert artifact_sink_testing.of_kind(PAGE_EVIDENCE)[0].content == expected_content
        actual_emit_record: logging.LogRecord = next(
            actual_log_record for actual_log_record in record_capture.records if AttributeKey.ARTIFACT_FILENAME in actual_log_record.__dict__
        )
        AsserterLogRecord.assert_record(expected_emit_record, actual_emit_record)

    async def test_StepScope_WhenAnArtifactIsEmitted_ThenItDescribesItselfToTheSink(
        self, artifact_sink_testing: ArtifactSinkTesting, run_logger: logging.Logger
    ) -> None:
        # Arrange - the sink can persist it blindly: what it holds, its media type and its bytes travel with it
        work_item: WorkItem = create_random_work_item()
        emitted_content: bytes = b"{}"
        pipeline_run: PipelineRun = PipelineRun(pipeline_name=PIPELINE_NAME, sink=artifact_sink_testing, logger=run_logger)
        expected_description: tuple[str, str, bytes] = (PAGE_EVIDENCE.key, PAGE_EVIDENCE.content_type, emitted_content)

        # Act
        async with pipeline_run, pipeline_run.open_work_item(work_item) as work_item_scope, work_item_scope.step(METADATA_AUDIT) as step_scope:
            await step_scope.emit(PAGE_EVIDENCE, emitted_content)

        # Assert
        actual_step_artifact: StepArtifact = next(
            actual_recorded for actual_recorded in artifact_sink_testing.artifacts if isinstance(actual_recorded, StepArtifact)
        )
        assert (actual_step_artifact.artifact_type, actual_step_artifact.content_type, actual_step_artifact.content) == expected_description

    async def test_StepScope_WhenStepsEmitPastStepNine_ThenADirectoryListingSortsInPipelineOrder(
        self, artifact_sink_testing: ArtifactSinkTesting, run_logger: logging.Logger
    ) -> None:
        # Arrange
        work_item: WorkItem = create_random_work_item()
        pipeline_run: PipelineRun = PipelineRun(pipeline_name=PIPELINE_NAME, sink=artifact_sink_testing, logger=run_logger)
        expected_filenames_in_pipeline_order: list[str] = [
            f"{work_item.stem}_step_{step_number:02d}_page_evidence.json" for step_number in (1, 2, 9, 10, 11)
        ]

        # Act - steps are declared out of order on purpose
        async with pipeline_run, pipeline_run.open_work_item(work_item) as work_item_scope:
            for step_number in (10, 2, 1, 9, 11):
                async with work_item_scope.step(Step(step_number, f"Step {step_number}")) as step_scope:
                    await step_scope.emit(PAGE_EVIDENCE, b"")

        # Assert
        actual_filenames_sorted_as_a_listing: list[str] = sorted(
            actual_artifact.filename for actual_artifact in artifact_sink_testing.artifacts if isinstance(actual_artifact, StepArtifact)
        )
        assert actual_filenames_sorted_as_a_listing == expected_filenames_in_pipeline_order

    @pytest.mark.parametrize("unsafe_discriminator", ["a/b", "page 3", "..\\x", ""])
    async def test_StepScope_WhenTheDiscriminatorIsUnsafeForAFilename_ThenTheEmitIsRefused(
        self, unsafe_discriminator: str, artifact_sink_testing: ArtifactSinkTesting, run_logger: logging.Logger
    ) -> None:
        # Arrange
        work_item: WorkItem = create_random_work_item()
        pipeline_run: PipelineRun = PipelineRun(pipeline_name=PIPELINE_NAME, sink=artifact_sink_testing, logger=run_logger)
        expected_exception: ExpectedException = ExpectedException(
            InvalidDeclarationError, message_phrases=["discriminator", "letters, digits, dot, underscore and hyphen"]
        )

        # Act
        with pytest.raises(InvalidDeclarationError) as actual_raised:
            async with pipeline_run, pipeline_run.open_work_item(work_item) as work_item_scope, work_item_scope.step(METADATA_AUDIT) as step_scope:
                await step_scope.emit(PAGE_EVIDENCE, b"{}", discriminator=unsafe_discriminator)

        # Assert
        AsserterException.assert_exception(expected_exception, actual_raised.value)


@pytest.mark.acceptance
class TestArtifactKindDeclaration:
    @pytest.mark.parametrize("vague_key", ["result", "output", "data", "artifact", "payload", "results"])
    def test_ArtifactKind_WhenTheKeyIsVague_ThenItIsRefused(self, vague_key: str) -> None:
        # Arrange - a kind named for its role can be found again; "result" cannot
        expected_exception: ExpectedException = ExpectedException(InvalidDeclarationError, message_phrases=[vague_key, "too vague"])

        # Act
        with pytest.raises(InvalidDeclarationError) as actual_raised:
            ArtifactKind(vague_key, "json", "application/json")

        # Assert
        AsserterException.assert_exception(expected_exception, actual_raised.value)

    @pytest.mark.parametrize("malformed_key", ["Page Evidence", "page-evidence", "_page", "page__evidence"])
    def test_ArtifactKind_WhenTheKeyIsMalformed_ThenItIsRefused(self, malformed_key: str) -> None:
        # Arrange
        expected_exception: ExpectedException = ExpectedException(InvalidDeclarationError, message_phrases=[malformed_key, "lowercase words"])

        # Act
        with pytest.raises(InvalidDeclarationError) as actual_raised:
            ArtifactKind(malformed_key, "json", "application/json")

        # Assert
        AsserterException.assert_exception(expected_exception, actual_raised.value)

    def test_ArtifactKind_WhenTheExtensionCarriesADot_ThenItIsRefused(self) -> None:
        # Arrange
        dotted_extension: str = ".json"
        expected_exception: ExpectedException = ExpectedException(InvalidDeclarationError, message_phrases=[dotted_extension, "without a dot"])

        # Act
        with pytest.raises(InvalidDeclarationError) as actual_raised:
            ArtifactKind("page_evidence", dotted_extension, "application/json")

        # Assert
        AsserterException.assert_exception(expected_exception, actual_raised.value)

    def test_ArtifactKind_WhenNoRoleIsGiven_ThenTheArtifactIsInterim(self) -> None:
        # Arrange
        expected_role: ArtifactRole = ArtifactRole.INTERIM

        # Act
        actual_artifact_kind: ArtifactKind = ArtifactKind("page_evidence", "json", "application/json")

        # Assert
        assert actual_artifact_kind.role is expected_role


@pytest.mark.acceptance
class TestWorkItemIdentity:
    def test_WorkItem_WhenTheNameHasAnExtension_ThenTheStemDropsIt(self) -> None:
        # Arrange
        expected_stem: str = create_random_document_stem()

        # Act
        actual_work_item: WorkItem = WorkItem(secrets.token_hex(_RANDOM_SUFFIX_BYTES), f"{expected_stem}.pdf")

        # Assert
        assert actual_work_item.stem == expected_stem

    def test_WorkItem_WhenTheNameHasNoExtension_ThenTheStemIsTheName(self) -> None:
        # Arrange
        work_item_name: str = f"request-{secrets.token_hex(_RANDOM_SUFFIX_BYTES)}"

        # Act
        actual_work_item: WorkItem = WorkItem(secrets.token_hex(_RANDOM_SUFFIX_BYTES), work_item_name)

        # Assert
        assert actual_work_item.stem == work_item_name

    def test_WorkItem_WhenTheIdentityIsBlank_ThenItIsRefused(self) -> None:
        # Arrange
        expected_exception: ExpectedException = ExpectedException(InvalidDeclarationError, message_phrases=["id must not be blank"])

        # Act
        with pytest.raises(InvalidDeclarationError) as actual_raised:
            WorkItem(" ", f"{create_random_document_stem()}.pdf")

        # Assert
        AsserterException.assert_exception(expected_exception, actual_raised.value)

    def test_WorkItem_WhenTheNameIsBlank_ThenItIsRefused(self) -> None:
        # Arrange
        expected_exception: ExpectedException = ExpectedException(InvalidDeclarationError, message_phrases=["name must not be blank"])

        # Act
        with pytest.raises(InvalidDeclarationError) as actual_raised:
            WorkItem(secrets.token_hex(_RANDOM_SUFFIX_BYTES), " ")

        # Assert
        AsserterException.assert_exception(expected_exception, actual_raised.value)


@pytest.mark.acceptance
class TestRunLevelArtifact:
    async def test_PipelineRun_WhenTheRunCloses_ThenTheManifestHasNoWorkItemPrefix(
        self, artifact_sink_testing: ArtifactSinkTesting, run_logger: logging.Logger
    ) -> None:
        # Arrange
        pipeline_run: PipelineRun = PipelineRun(pipeline_name=PIPELINE_NAME, sink=artifact_sink_testing, logger=run_logger)
        expected_filenames: list[str] = [MANIFEST_FILENAME]

        # Act
        async with pipeline_run:
            pass

        # Assert
        AsserterArtifacts.assert_exactly_these_filenames_in_order(expected_filenames, artifact_sink_testing.artifacts)
