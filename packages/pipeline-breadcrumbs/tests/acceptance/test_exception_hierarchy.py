# Acceptance tests for the sample's one exception hierarchy: every exception the library raises descends
# through the business or the technical branch, so a host's boundary can tell a failure the caller can
# correct from one the system's owner must correct, and the abstract bases themselves are never raised.

import logging
import secrets
from collections.abc import Sequence
from pathlib import Path
from typing import Final, final, override

import pytest
from breadcrumbs_acceptance_support.asserters.asserter_exception import ExceptionAsserter, ExpectedException
from breadcrumbs_acceptance_support.data_generators import create_random_pipeline_name, create_random_work_item

from pipeline_breadcrumbs import (
    AbstractExceptionRaisedException,
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
    StepAlreadyEnteredException,
    StepScope,
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


async def emit_page_text_for_each_work_item(pipeline_run: PipelineRun, work_items: Sequence[WorkItem]) -> None:
    async with pipeline_run:
        for work_item in work_items:
            step_scope: StepScope
            async with pipeline_run.open_work_item(work_item) as work_item_scope, work_item_scope.step(LOAD_PAGES) as step_scope:
                await step_scope.emit(PAGE_TEXT, work_item.id.encode())


async def enter_one_step_scope_twice(pipeline_run: PipelineRun, work_item: WorkItem) -> None:
    async with pipeline_run, pipeline_run.open_work_item(work_item) as work_item_scope:
        step_scope: StepScope = work_item_scope.step(LOAD_PAGES)
        async with step_scope:
            pass
        async with step_scope:
            pass


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

    async def test_PipelineRun_WhenTwoWorkItemsShareAFolderName_ThenTheCallerCatchesItAsABusinessException(
        self, tmp_path: Path, run_logger: logging.Logger
    ) -> None:
        # Arrange - the caller named both work items, so the caller can tell them apart; the run must not report it as a storage failure
        shared_name: str = f"Contract {secrets.token_hex(_RANDOM_SUFFIX_BYTES)}"
        first_work_item: WorkItem = WorkItem(secrets.token_hex(_RANDOM_SUFFIX_BYTES), f"{shared_name}.pdf")
        second_work_item: WorkItem = WorkItem(secrets.token_hex(_RANDOM_SUFFIX_BYTES), f"{shared_name}.docx")
        pipeline_run: PipelineRun = PipelineRun(
            pipeline_name=create_random_pipeline_name(), artifact_sink=ArtifactSinkFileSystem(tmp_path), logger=run_logger
        )
        expected_exception: ExpectedException = ExpectedException(
            WorkItemFolderCollisionException, message_phrases=[first_work_item.id, second_work_item.id, shared_name, "must be unique within a run"]
        )

        # Act
        with pytest.raises(PipelineBreadcrumbsBusinessBaseException) as actual_raised:
            await emit_page_text_for_each_work_item(pipeline_run, [first_work_item, second_work_item])

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

    async def test_StepScope_WhenEnteredASecondTime_ThenTheHostCatchesItAsATechnicalException(
        self, artifact_sink_testing: ArtifactSinkTesting, run_logger: logging.Logger
    ) -> None:
        # Arrange - no data causes it: the pipeline's code reuses one step scope for two openings
        pipeline_run: PipelineRun = PipelineRun(pipeline_name=create_random_pipeline_name(), artifact_sink=artifact_sink_testing, logger=run_logger)
        expected_exception: ExpectedException = ExpectedException(
            StepAlreadyEnteredException, message_phrases=["1 Load Pages", "was already entered"]
        )

        # Act
        with pytest.raises(PipelineBreadcrumbsTechnicalBaseException) as actual_raised:
            await enter_one_step_scope_twice(pipeline_run, create_random_work_item())

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
        expected_exception: ExpectedException = ExpectedException(
            AbstractExceptionRaisedException, message_phrases=[abstract_exception_type.__name__, "is abstract"]
        )

        # Act
        with pytest.raises(AbstractExceptionRaisedException) as actual_raised:
            abstract_exception_type(f"Failure {secrets.token_hex(_RANDOM_SUFFIX_BYTES)}")

        # Assert
        ExceptionAsserter.assert_expected_and_actual_are_equal(expected_exception, actual_raised.value)
