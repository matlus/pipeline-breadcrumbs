# Acceptance tests for emitting artifacts: a step hands over bytes and a declared kind, and the
# artifact derives its own name. Observed through the artifacts a recording sink received and the
# progress line the emit wrote.

import logging
import secrets
from collections.abc import Sequence
from typing import Final

import pytest
from breadcrumbs_acceptance_support.asserters.asserter_artifacts import ArtifactFilenamesAsserter, EmittedArtifactAsserter
from breadcrumbs_acceptance_support.asserters.asserter_exception import ExceptionAsserter, ExpectedException
from breadcrumbs_acceptance_support.asserters.asserter_log_record import ExpectedLogRecord, LogRecordAsserter
from breadcrumbs_acceptance_support.data_generators import create_random_discriminator, create_random_pipeline_name, create_random_work_item

from pipeline_breadcrumbs import (
    MANIFEST_KIND,
    ArtifactKind,
    ArtifactRole,
    AttributeKey,
    InvalidDeclarationException,
    PipelineRun,
    RunArtifact,
    Step,
    StepArtifact,
    WorkItem,
    safe_path_component,
)
from pipeline_breadcrumbs.testing import ArtifactSinkTesting, RecordCapture

MANIFEST_FILENAME: Final[str] = "manifest.json"
METADATA_AUDIT: Final[Step] = Step(2, "Metadata Audit")
PAGE_EVIDENCE: Final[ArtifactKind] = ArtifactKind("page_evidence", "json", "application/json")
RUN_SETTINGS: Final[ArtifactKind] = ArtifactKind("run_settings", "json", "application/json")
_RANDOM_SUFFIX_BYTES: Final[int] = 4


def create_random_document_stem() -> str:
    return f"Document {secrets.token_hex(_RANDOM_SUFFIX_BYTES)}"


def create_random_model_identifier() -> str:
    """A name that is not a file name: a `/` separates the publisher, and the last dot belongs to the version."""
    return f"publisher-{secrets.token_hex(_RANDOM_SUFFIX_BYTES)}/model-1.{secrets.randbelow(100)}"


def _retrieve_emit_record(actual_log_records: Sequence[logging.LogRecord]) -> logging.LogRecord:
    actual_emit_log_record: logging.LogRecord | None = next(
        (actual_log_record for actual_log_record in actual_log_records if AttributeKey.ARTIFACT_FILENAME in actual_log_record.__dict__), None
    )
    actual_messages: list[str] = [actual_log_record.getMessage() for actual_log_record in actual_log_records]
    assert actual_emit_log_record is not None, f"no record names an emitted artifact; the messages were {actual_messages!r}"
    return actual_emit_log_record


@pytest.mark.acceptance
class TestEmit:
    async def test_StepScope_WhenAnArtifactIsEmitted_ThenTheSinkReceivesItAndTheEmitIsLogged(
        self, artifact_sink_testing: ArtifactSinkTesting, run_logger: logging.Logger, record_capture: RecordCapture
    ) -> None:
        # Arrange
        pipeline_name: str = create_random_pipeline_name()
        work_item: WorkItem = create_random_work_item()
        expected_content: bytes = b'{"ok": true}'
        discriminator: str = create_random_discriminator()
        pipeline_run: PipelineRun = PipelineRun(pipeline_name=pipeline_name, artifact_sink=artifact_sink_testing, logger=run_logger)
        expected_filename: str = f"{work_item.stem}_step_02_page_evidence_{discriminator}.json"
        expected_emit_log_record: ExpectedLogRecord = ExpectedLogRecord(
            message=f"Emitted artifact: {expected_filename} (12 B)",
            attribute_value_by_key={AttributeKey.ARTIFACT_FILENAME: expected_filename, AttributeKey.ARTIFACT_BYTES: len(expected_content)},
        )

        # Act
        async with pipeline_run, pipeline_run.open_work_item(work_item) as work_item_scope, work_item_scope.step(METADATA_AUDIT) as step_scope:
            actual_emitted_step_artifact: StepArtifact = await step_scope.emit(PAGE_EVIDENCE, expected_content, discriminator=discriminator)

        # Assert
        EmittedArtifactAsserter.assert_expected_and_actual_are_equal(
            expected_filename, expected_content, actual_emitted_step_artifact, artifact_sink_testing.artifacts
        )
        LogRecordAsserter.assert_expected_and_actual_are_equal(expected_emit_log_record, _retrieve_emit_record(record_capture.records))

    async def test_StepScope_WhenAnArtifactIsEmitted_ThenItDescribesItselfToTheSink(
        self, artifact_sink_testing: ArtifactSinkTesting, run_logger: logging.Logger
    ) -> None:
        # Arrange - the sink can persist it blindly: what it holds, its media type and its bytes travel with it
        pipeline_name: str = create_random_pipeline_name()
        work_item: WorkItem = create_random_work_item()
        emitted_content: bytes = b"{}"
        pipeline_run: PipelineRun = PipelineRun(pipeline_name=pipeline_name, artifact_sink=artifact_sink_testing, logger=run_logger)
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
        pipeline_name: str = create_random_pipeline_name()
        work_item: WorkItem = create_random_work_item()
        pipeline_run: PipelineRun = PipelineRun(pipeline_name=pipeline_name, artifact_sink=artifact_sink_testing, logger=run_logger)
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
        pipeline_name: str = create_random_pipeline_name()
        work_item: WorkItem = create_random_work_item()
        pipeline_run: PipelineRun = PipelineRun(pipeline_name=pipeline_name, artifact_sink=artifact_sink_testing, logger=run_logger)
        expected_exception: ExpectedException = ExpectedException(
            InvalidDeclarationException, message_phrases=["discriminator", "letters, digits, dot, underscore and hyphen"]
        )

        # Act
        with pytest.raises(InvalidDeclarationException) as actual_raised:
            async with pipeline_run, pipeline_run.open_work_item(work_item) as work_item_scope, work_item_scope.step(METADATA_AUDIT) as step_scope:
                await step_scope.emit(PAGE_EVIDENCE, b"{}", discriminator=unsafe_discriminator)

        # Assert
        ExceptionAsserter.assert_expected_and_actual_are_equal(expected_exception, actual_raised.value)


@pytest.mark.acceptance
class TestArtifactKindDeclaration:
    @pytest.mark.parametrize("vague_key", ["result", "output", "data", "artifact", "payload", "results"])
    def test_ArtifactKind_WhenTheKeyIsVague_ThenItIsRefused(self, vague_key: str) -> None:
        # Arrange - a kind named for its role can be found again; "result" cannot
        expected_exception: ExpectedException = ExpectedException(InvalidDeclarationException, message_phrases=[vague_key, "too vague"])

        # Act
        with pytest.raises(InvalidDeclarationException) as actual_raised:
            ArtifactKind(vague_key, "json", "application/json")

        # Assert
        ExceptionAsserter.assert_expected_and_actual_are_equal(expected_exception, actual_raised.value)

    @pytest.mark.parametrize("malformed_key", ["Page Evidence", "page-evidence", "_page", "page__evidence"])
    def test_ArtifactKind_WhenTheKeyIsMalformed_ThenItIsRefused(self, malformed_key: str) -> None:
        # Arrange
        expected_exception: ExpectedException = ExpectedException(InvalidDeclarationException, message_phrases=[malformed_key, "lowercase words"])

        # Act
        with pytest.raises(InvalidDeclarationException) as actual_raised:
            ArtifactKind(malformed_key, "json", "application/json")

        # Assert
        ExceptionAsserter.assert_expected_and_actual_are_equal(expected_exception, actual_raised.value)

    def test_ArtifactKind_WhenTheExtensionCarriesADot_ThenItIsRefused(self) -> None:
        # Arrange
        dotted_extension: str = ".json"
        expected_exception: ExpectedException = ExpectedException(InvalidDeclarationException, message_phrases=[dotted_extension, "without a dot"])

        # Act
        with pytest.raises(InvalidDeclarationException) as actual_raised:
            ArtifactKind("page_evidence", dotted_extension, "application/json")

        # Assert
        ExceptionAsserter.assert_expected_and_actual_are_equal(expected_exception, actual_raised.value)

    def test_ArtifactKind_WhenNoRoleIsGiven_ThenTheArtifactIsInterim(self) -> None:
        # Arrange
        expected_artifact_role: ArtifactRole = ArtifactRole.INTERIM

        # Act
        actual_artifact_kind: ArtifactKind = ArtifactKind("page_evidence", "json", "application/json")

        # Assert
        assert actual_artifact_kind.role is expected_artifact_role


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
        expected_work_item_name: str = f"request-{secrets.token_hex(_RANDOM_SUFFIX_BYTES)}"

        # Act
        actual_work_item: WorkItem = WorkItem(secrets.token_hex(_RANDOM_SUFFIX_BYTES), expected_work_item_name)

        # Assert
        assert actual_work_item.stem == expected_work_item_name

    def test_WorkItem_WhenTheNameHasCharactersAFileSystemRefuses_ThenTheStemReplacesThemAndStillDropsTheExtension(self) -> None:
        # Arrange - a `/` in the name would otherwise name a subfolder, and `:` and `?` are refused on Windows
        document_stem: str = create_random_document_stem()
        expected_stem: str = f"Q3_ {document_stem} _ Draft_"

        # Act
        actual_work_item: WorkItem = WorkItem(secrets.token_hex(_RANDOM_SUFFIX_BYTES), f"Q3: {document_stem} / Draft?.pdf")

        # Assert
        assert actual_work_item.stem == expected_stem

    def test_WorkItem_WhenAFileStemIsGiven_ThenItIsTheStemExactlyAsWritten(self) -> None:
        # Arrange - a model identifier is not a file name: its last dot is part of the version, not an extension
        model_identifier: str = create_random_model_identifier()
        expected_stem: str = safe_path_component(model_identifier)

        # Act
        actual_work_item: WorkItem = WorkItem(id=model_identifier, name=model_identifier, file_stem=expected_stem)

        # Assert
        assert actual_work_item.stem == expected_stem

    def test_WorkItem_WhenTheFileStemIsBlank_ThenItIsRefused(self) -> None:
        # Arrange
        expected_exception: ExpectedException = ExpectedException(InvalidDeclarationException, message_phrases=["file_stem must not be blank"])

        # Act
        with pytest.raises(InvalidDeclarationException) as actual_raised:
            WorkItem(secrets.token_hex(_RANDOM_SUFFIX_BYTES), create_random_model_identifier(), file_stem=" ")

        # Assert
        ExceptionAsserter.assert_expected_and_actual_are_equal(expected_exception, actual_raised.value)

    def test_WorkItem_WhenTheFileStemIsNotFileSafe_ThenItIsRefusedWithTheSafeSpelling(self) -> None:
        # Arrange
        model_identifier: str = create_random_model_identifier()
        expected_exception: ExpectedException = ExpectedException(
            InvalidDeclarationException, message_phrases=["must be safe to use as a file name", repr(safe_path_component(model_identifier))]
        )

        # Act
        with pytest.raises(InvalidDeclarationException) as actual_raised:
            WorkItem(secrets.token_hex(_RANDOM_SUFFIX_BYTES), model_identifier, file_stem=model_identifier)

        # Assert
        ExceptionAsserter.assert_expected_and_actual_are_equal(expected_exception, actual_raised.value)

    async def test_StepScope_WhenTheWorkItemHasAFileStem_ThenTheArtifactFilenameStartsWithIt(
        self, artifact_sink_testing: ArtifactSinkTesting, run_logger: logging.Logger
    ) -> None:
        # Arrange
        model_identifier: str = create_random_model_identifier()
        file_stem: str = safe_path_component(model_identifier)
        work_item: WorkItem = WorkItem(id=model_identifier, name=model_identifier, file_stem=file_stem)
        pipeline_run: PipelineRun = PipelineRun(pipeline_name=create_random_pipeline_name(), artifact_sink=artifact_sink_testing, logger=run_logger)
        expected_filenames: list[str] = [f"{file_stem}_step_02_page_evidence.json", MANIFEST_FILENAME]

        # Act
        async with pipeline_run, pipeline_run.open_work_item(work_item) as work_item_scope, work_item_scope.step(METADATA_AUDIT) as step_scope:
            await step_scope.emit(PAGE_EVIDENCE, b"{}")

        # Assert
        ArtifactFilenamesAsserter.assert_expected_and_actual_are_equal(expected_filenames, artifact_sink_testing.artifacts)

    def test_WorkItem_WhenTheIdentityIsBlank_ThenItIsRefused(self) -> None:
        # Arrange
        expected_exception: ExpectedException = ExpectedException(InvalidDeclarationException, message_phrases=["id must not be blank"])

        # Act
        with pytest.raises(InvalidDeclarationException) as actual_raised:
            WorkItem(" ", f"{create_random_document_stem()}.pdf")

        # Assert
        ExceptionAsserter.assert_expected_and_actual_are_equal(expected_exception, actual_raised.value)

    def test_WorkItem_WhenTheNameIsBlank_ThenItIsRefused(self) -> None:
        # Arrange
        expected_exception: ExpectedException = ExpectedException(InvalidDeclarationException, message_phrases=["name must not be blank"])

        # Act
        with pytest.raises(InvalidDeclarationException) as actual_raised:
            WorkItem(secrets.token_hex(_RANDOM_SUFFIX_BYTES), " ")

        # Assert
        ExceptionAsserter.assert_expected_and_actual_are_equal(expected_exception, actual_raised.value)


@pytest.mark.acceptance
class TestRunLevelArtifact:
    async def test_PipelineRun_WhenTheRunCloses_ThenTheManifestHasNoWorkItemPrefix(
        self, artifact_sink_testing: ArtifactSinkTesting, run_logger: logging.Logger
    ) -> None:
        # Arrange
        pipeline_name: str = create_random_pipeline_name()
        pipeline_run: PipelineRun = PipelineRun(pipeline_name=pipeline_name, artifact_sink=artifact_sink_testing, logger=run_logger)
        expected_filenames: list[str] = [MANIFEST_FILENAME]

        # Act
        async with pipeline_run:
            pass

        # Assert
        ArtifactFilenamesAsserter.assert_expected_and_actual_are_equal(expected_filenames, artifact_sink_testing.artifacts)

    async def test_PipelineRun_WhenARunArtifactIsEmitted_ThenTheSinkReceivesItUnderItsKindAndTheEmitIsLogged(
        self, artifact_sink_testing: ArtifactSinkTesting, run_logger: logging.Logger, record_capture: RecordCapture
    ) -> None:
        # Arrange
        pipeline_name: str = create_random_pipeline_name()
        expected_content: bytes = f'{{"pipeline": "{pipeline_name}"}}'.encode()
        pipeline_run: PipelineRun = PipelineRun(pipeline_name=pipeline_name, artifact_sink=artifact_sink_testing, logger=run_logger)
        expected_filename: str = "run_settings.json"
        expected_emit_log_record: ExpectedLogRecord = ExpectedLogRecord(
            message=f"Emitted artifact: {expected_filename} ({len(expected_content)} B)",
            attribute_value_by_key={AttributeKey.ARTIFACT_FILENAME: expected_filename, AttributeKey.ARTIFACT_BYTES: len(expected_content)},
        )

        # Act
        async with pipeline_run:
            actual_emitted_run_artifact: RunArtifact = await pipeline_run.emit(RUN_SETTINGS, expected_content)

        # Assert
        EmittedArtifactAsserter.assert_expected_and_actual_are_equal(
            expected_filename, expected_content, actual_emitted_run_artifact, artifact_sink_testing.artifacts
        )
        LogRecordAsserter.assert_expected_and_actual_are_equal(expected_emit_log_record, _retrieve_emit_record(record_capture.records))

    async def test_PipelineRun_WhenARunArtifactUsesTheManifestKind_ThenItIsRefused(
        self, artifact_sink_testing: ArtifactSinkTesting, run_logger: logging.Logger
    ) -> None:
        # Arrange - the run writes its own manifest when it closes, so a second one would overwrite or be overwritten
        pipeline_run: PipelineRun = PipelineRun(pipeline_name=create_random_pipeline_name(), artifact_sink=artifact_sink_testing, logger=run_logger)
        expected_exception: ExpectedException = ExpectedException(InvalidDeclarationException, message_phrases=["is reserved for the manifest"])

        # Act
        with pytest.raises(InvalidDeclarationException) as actual_raised:
            async with pipeline_run:
                await pipeline_run.emit(MANIFEST_KIND, b"{}")

        # Assert
        ExceptionAsserter.assert_expected_and_actual_are_equal(expected_exception, actual_raised.value)
