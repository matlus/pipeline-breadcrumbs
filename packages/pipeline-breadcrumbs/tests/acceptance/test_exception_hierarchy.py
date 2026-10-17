# Acceptance tests for the sample's one exception hierarchy: every exception the library raises descends
# through the business or the technical branch, so a host's boundary can tell a failure the caller can
# correct from one the system's owner must correct, and the abstract bases themselves are never raised.

import logging
import secrets
from pathlib import Path
from typing import Final, final, override

import pytest
from breadcrumbs_acceptance_support.asserters.asserter_exception import ExceptionAsserter, ExpectedException
from breadcrumbs_acceptance_support.data_generators import create_random_pipeline_name, create_random_work_item

from pipeline_breadcrumbs import (
    Artifact,
    ArtifactKind,
    ArtifactSinkException,
    ArtifactSinkProtocol,
    InvalidDeclarationException,
    PipelineBreadcrumbsBaseException,
    PipelineBreadcrumbsBusinessBaseException,
    PipelineBreadcrumbsTechnicalBaseException,
    PipelineRun,
    Step,
    StepArtifact,
    StepPath,
    WorkItem,
    WorkItemNotOpenException,
    WorkItemScope,
)
from pipeline_breadcrumbs.hosting import ArtifactSinkFileSystem, WorkItemFolderCollisionException
from pipeline_breadcrumbs.testing import ArtifactSinkTesting

LOAD_PAGES: Final[Step] = Step(1, "Load Pages")
PAGE_TEXT: Final[ArtifactKind] = ArtifactKind("page_text", "txt", "text/plain")
STORAGE_OUTAGE_MESSAGE: Final[str] = "blob storage unreachable"
_RANDOM_SUFFIX_BYTES: Final[int] = 4


@final
class ArtifactSinkUnreachable(ArtifactSinkProtocol):
    @override
    async def persist(self, artifact: Artifact) -> None:
        raise ConnectionError(STORAGE_OUTAGE_MESSAGE)


@pytest.mark.acceptance
class TestExceptionBranches:
    def test_Step_WhenDeclaredWithARefusedValue_ThenTheCallerCatchesItAsABusinessException(self) -> None:
        # Arrange
        expected_exception: ExpectedException = ExpectedException(InvalidDeclarationException, message_phrases=["between 1 and 99"])

        # Act
        with pytest.raises(PipelineBreadcrumbsBusinessBaseException) as actual_raised:
            Step(0, "Load Pages")

        # Assert
        ExceptionAsserter.assert_expected_and_actual_are_equal(expected_exception, actual_raised.value)

    async def test_ArtifactSinkFileSystem_WhenTwoWorkItemsShareAFolderName_ThenTheCallerCatchesItAsABusinessException(self, tmp_path: Path) -> None:
        # Arrange - the caller named both work items, so the caller can tell them apart
        shared_name: str = f"Contract {secrets.token_hex(_RANDOM_SUFFIX_BYTES)}"
        first_work_item: WorkItem = WorkItem(secrets.token_hex(_RANDOM_SUFFIX_BYTES), f"{shared_name}.pdf")
        second_work_item: WorkItem = WorkItem(secrets.token_hex(_RANDOM_SUFFIX_BYTES), f"{shared_name}.docx")
        artifact_sink_file_system: ArtifactSinkFileSystem = ArtifactSinkFileSystem(tmp_path)
        await artifact_sink_file_system.persist(StepArtifact(PAGE_TEXT, b"first", first_work_item, StepPath((1,))))
        expected_exception: ExpectedException = ExpectedException(WorkItemFolderCollisionException, message_phrases=["must be unique within a run"])

        # Act
        with pytest.raises(PipelineBreadcrumbsBusinessBaseException) as actual_raised:
            await artifact_sink_file_system.persist(StepArtifact(PAGE_TEXT, b"second", second_work_item, StepPath((1,))))

        # Assert
        ExceptionAsserter.assert_expected_and_actual_are_equal(expected_exception, actual_raised.value)

    async def test_PipelineRun_WhenTheSinkCannotPersist_ThenTheHostCatchesItAsATechnicalException(self, run_logger: logging.Logger) -> None:
        # Arrange - a storage outage is the system owner's to correct; the request was fine
        pipeline_run: PipelineRun = PipelineRun(
            pipeline_name=create_random_pipeline_name(), artifact_sink=ArtifactSinkUnreachable(), logger=run_logger
        )
        expected_exception: ExpectedException = ExpectedException(
            ArtifactSinkException, message_phrases=["manifest.json"], cause_type=ConnectionError
        )

        # Act
        with pytest.raises(PipelineBreadcrumbsTechnicalBaseException) as actual_raised:
            async with pipeline_run:
                pass

        # Assert
        ExceptionAsserter.assert_expected_and_actual_are_equal(expected_exception, actual_raised.value)

    async def test_WorkItemScope_WhenUsedBeforeItIsOpened_ThenTheHostCatchesItAsATechnicalException(
        self, artifact_sink_testing: ArtifactSinkTesting, run_logger: logging.Logger
    ) -> None:
        # Arrange - no data causes it: the pipeline's code calls the scope in the wrong order
        pipeline_run: PipelineRun = PipelineRun(pipeline_name=create_random_pipeline_name(), artifact_sink=artifact_sink_testing, logger=run_logger)
        work_item_scope: WorkItemScope = pipeline_run.open_work_item(create_random_work_item())
        expected_exception: ExpectedException = ExpectedException(WorkItemNotOpenException, message_phrases=["is not open"])

        # Act
        with pytest.raises(PipelineBreadcrumbsTechnicalBaseException) as actual_raised:
            work_item_scope.step(LOAD_PAGES)

        # Assert
        ExceptionAsserter.assert_expected_and_actual_are_equal(expected_exception, actual_raised.value)


@pytest.mark.acceptance
class TestAbstractExceptionBases:
    @pytest.mark.parametrize(
        "abstract_exception_type",
        [PipelineBreadcrumbsBaseException, PipelineBreadcrumbsBusinessBaseException, PipelineBreadcrumbsTechnicalBaseException],
    )
    def test_PipelineBreadcrumbsBaseException_WhenAnAbstractBaseIsRaised_ThenItIsRefused(
        self, abstract_exception_type: type[PipelineBreadcrumbsBaseException]
    ) -> None:
        # Arrange - only a concrete, @final exception names a specific failure
        expected_exception: ExpectedException = ExpectedException(TypeError, message_phrases=[abstract_exception_type.__name__, "is abstract"])

        # Act
        with pytest.raises(TypeError) as actual_raised:
            abstract_exception_type(f"Failure {secrets.token_hex(_RANDOM_SUFFIX_BYTES)}")

        # Assert
        ExceptionAsserter.assert_expected_and_actual_are_equal(expected_exception, actual_raised.value)
