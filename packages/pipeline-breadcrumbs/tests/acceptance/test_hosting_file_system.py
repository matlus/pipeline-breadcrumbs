# Acceptance tests for the host-side helpers that keep a run on disk: the file-system sink, the
# per-run folder and the attached run log. Black-box through their public classes and functions,
# against a real temporary folder.

import logging
import secrets
from pathlib import Path
from typing import Final

import pytest
from breadcrumbs_acceptance_support.asserters.asserter_exception import AsserterException, ExpectedException
from breadcrumbs_acceptance_support.asserters.asserter_rendered_text import AsserterRenderedText, ExpectedRenderedText
from breadcrumbs_acceptance_support.clock_testing import ClockTesting
from breadcrumbs_acceptance_support.data_generators import create_random_discriminator, create_random_pipeline_name, create_random_work_item

from pipeline_breadcrumbs import (
    ArtifactKind,
    BreadcrumbFormatter,
    PipelineRun,
    RunArtifact,
    Step,
    StepArtifact,
    StepPath,
    TimeDisplay,
    WorkItem,
)
from pipeline_breadcrumbs.hosting import (
    ArtifactSinkFileSystem,
    WorkItemFolderCollisionError,
    attached_run_log,
    create_run_folder,
    safe_path_component,
)

MANIFEST_FILENAME: Final[str] = "manifest.json"
RUN_LOG_FILENAME: Final[str] = "run.log"
PAGE_IMAGE: Final[ArtifactKind] = ArtifactKind("page_image", "png", "image/png")
PAGE_TEXT: Final[ArtifactKind] = ArtifactKind("page_text", "txt", "text/plain")
MANIFEST: Final[ArtifactKind] = ArtifactKind("manifest", "json", "application/json")
LOAD_PAGES: Final[Step] = Step(1, "Load Pages")
# ClockTesting's fixed time of day, as a run folder name renders it.
CLOCK_TESTING_FOLDER_TIMESTAMP: Final[str] = "20261003_140322"
CLOCK_TESTING_FOLDER_TIMESTAMP_ONE_MINUTE_LATER: Final[str] = "20261003_140422"
_RANDOM_SUFFIX_BYTES: Final[int] = 4


def _read_written_bytes(written_path: Path) -> bytes:
    return written_path.read_bytes()


def _list_entry_names(folder: Path) -> list[str]:
    return sorted(entry.name for entry in folder.iterdir())


def _read_written_text(written_path: Path) -> str:
    return written_path.read_text(encoding="utf-8")


def create_random_label() -> str:
    return f"Contract {secrets.token_hex(_RANDOM_SUFFIX_BYTES)}"


def create_random_work_item_with_stem(stem: str, extension: str) -> WorkItem:
    return WorkItem(secrets.token_hex(_RANDOM_SUFFIX_BYTES), f"{stem}.{extension}")


@pytest.mark.acceptance
class TestSafePathComponent:
    def test_safe_path_component_WhenTheNameHasUnsafeCharacters_ThenTheyAreReplaced(self) -> None:
        # Arrange
        expected_component: str = "Q3_ Plan _ Draft_.pdf"

        # Act
        actual_component: str = safe_path_component("Q3: Plan / Draft?.pdf")

        # Assert
        assert actual_component == expected_component

    def test_safe_path_component_WhenTheNameEndsWithDotsAndSpaces_ThenTheyAreTrimmed(self) -> None:
        # Arrange - Windows refuses a trailing dot or space in a folder name
        expected_component: str = "report"

        # Act
        actual_component: str = safe_path_component("report. ")

        # Assert
        assert actual_component == expected_component

    def test_safe_path_component_WhenNothingSafeRemains_ThenItStillNamesAFolder(self) -> None:
        # Arrange
        expected_component: str = "_"

        # Act
        actual_component: str = safe_path_component("...")

        # Assert
        assert actual_component == expected_component


@pytest.mark.acceptance
class TestRunFolder:
    def test_create_run_folder_WhenCreated_ThenTheNameIsTimestampThenLabel(self, tmp_path: Path, clock_testing: ClockTesting) -> None:
        # Arrange
        run_folder_label: str = create_random_label()
        expected_folder: tuple[str, bool] = (f"{CLOCK_TESTING_FOLDER_TIMESTAMP}_{run_folder_label}", True)

        # Act
        actual_run_folder: Path = create_run_folder(tmp_path, run_folder_label, supplied_clock=clock_testing.clock)

        # Assert
        assert (actual_run_folder.name, actual_run_folder.is_dir()) == expected_folder

    def test_create_run_folder_WhenTwoRunsStartInTheSameSecond_ThenTheyDoNotCollide(self, tmp_path: Path, clock_testing: ClockTesting) -> None:
        # Arrange
        run_folder_label: str = create_random_label()
        expected_folder_names: tuple[str, str] = (
            f"{CLOCK_TESTING_FOLDER_TIMESTAMP}_{run_folder_label}",
            f"{CLOCK_TESTING_FOLDER_TIMESTAMP}_{run_folder_label}_2",
        )

        # Act
        actual_first_folder: Path = create_run_folder(tmp_path, run_folder_label, supplied_clock=clock_testing.clock)
        actual_second_folder: Path = create_run_folder(tmp_path, run_folder_label, supplied_clock=clock_testing.clock)

        # Assert
        assert (actual_first_folder.name, actual_second_folder.name) == expected_folder_names

    def test_create_run_folder_WhenTheSameFileIsRunLater_ThenTheEarlierRunIsKept(self, tmp_path: Path, clock_testing: ClockTesting) -> None:
        # Arrange
        run_folder_label: str = create_random_label()
        create_run_folder(tmp_path, run_folder_label, supplied_clock=clock_testing.clock)
        clock_testing.advance(60)
        expected_entry_names: list[str] = [
            f"{CLOCK_TESTING_FOLDER_TIMESTAMP}_{run_folder_label}",
            f"{CLOCK_TESTING_FOLDER_TIMESTAMP_ONE_MINUTE_LATER}_{run_folder_label}",
        ]

        # Act
        create_run_folder(tmp_path, run_folder_label, supplied_clock=clock_testing.clock)

        # Assert
        assert _list_entry_names(tmp_path) == expected_entry_names


@pytest.mark.acceptance
class TestArtifactSinkFileSystem:
    async def test_ArtifactSinkFileSystem_WhenAStepArtifactArrives_ThenItLandsInItsWorkItemsFolder(self, tmp_path: Path) -> None:
        # Arrange
        work_item: WorkItem = create_random_work_item()
        expected_content: bytes = secrets.token_bytes(_RANDOM_SUFFIX_BYTES)
        artifact_sink_file_system: ArtifactSinkFileSystem = ArtifactSinkFileSystem(tmp_path)
        discriminator: str = create_random_discriminator()
        expected_path: Path = tmp_path / work_item.stem / f"{work_item.stem}_step_01_page_text_{discriminator}.txt"

        # Act
        await artifact_sink_file_system(StepArtifact(PAGE_TEXT, expected_content, work_item, StepPath((1,)), discriminator=discriminator))

        # Assert
        assert _read_written_bytes(expected_path) == expected_content

    async def test_ArtifactSinkFileSystem_WhenARunArtifactArrives_ThenItSitsAtTheTop(self, tmp_path: Path) -> None:
        # Arrange
        expected_content: bytes = b"{}"
        artifact_sink_file_system: ArtifactSinkFileSystem = ArtifactSinkFileSystem(tmp_path)

        # Act
        await artifact_sink_file_system(RunArtifact(MANIFEST, expected_content))

        # Assert
        assert (tmp_path / MANIFEST_FILENAME).read_bytes() == expected_content

    async def test_ArtifactSinkFileSystem_WhenOneWorkItemHasManyKindsOfArtifact_ThenTheyShareOneFolderThatListsInStepOrder(
        self, tmp_path: Path
    ) -> None:
        # Arrange - the artifacts arrive in an order unrelated to their steps
        work_item: WorkItem = create_random_work_item()
        stem: str = work_item.stem
        artifact_sink_file_system: ArtifactSinkFileSystem = ArtifactSinkFileSystem(tmp_path)
        # One folder, no subfolders, and an alphabetical listing is the step order.
        expected_entries: list[tuple[str, bool]] = [
            (f"{stem}_step_01_page_image.png", True),
            (f"{stem}_step_02.09_page_image.png", True),
            (f"{stem}_step_02.10_page_text.txt", True),
            (f"{stem}_step_10_page_text.txt", True),
        ]

        # Act
        await artifact_sink_file_system(StepArtifact(PAGE_TEXT, b"c", work_item, StepPath((10,))))
        await artifact_sink_file_system(StepArtifact(PAGE_IMAGE, b"a", work_item, StepPath((2, 9))))
        await artifact_sink_file_system(StepArtifact(PAGE_TEXT, b"b", work_item, StepPath((2, 10))))
        await artifact_sink_file_system(StepArtifact(PAGE_IMAGE, b"d", work_item, StepPath((1,))))

        # Assert
        actual_entries: list[tuple[str, bool]] = [
            (actual_entry.name, actual_entry.is_file())
            for actual_entry in sorted((tmp_path / stem).iterdir(), key=lambda actual_path: actual_path.name)
        ]
        assert actual_entries == expected_entries

    async def test_ArtifactSinkFileSystem_WhenTwoWorkItemsShareAFolderName_ThenTheSecondIsRefusedInsteadOfOverwriting(self, tmp_path: Path) -> None:
        # Arrange
        shared_stem: str = create_random_label()
        first_work_item: WorkItem = create_random_work_item_with_stem(shared_stem, "pdf")
        second_work_item: WorkItem = create_random_work_item_with_stem(shared_stem, "docx")
        artifact_sink_file_system: ArtifactSinkFileSystem = ArtifactSinkFileSystem(tmp_path)
        await artifact_sink_file_system(StepArtifact(PAGE_TEXT, b"first", first_work_item, StepPath((1,))))
        expected_exception: ExpectedException = ExpectedException(
            WorkItemFolderCollisionError, message_phrases=[first_work_item.id, second_work_item.id, shared_stem, "must be unique within a run"]
        )

        # Act
        with pytest.raises(WorkItemFolderCollisionError) as actual_raised:
            await artifact_sink_file_system(StepArtifact(PAGE_TEXT, b"second", second_work_item, StepPath((1,))))

        # Assert
        AsserterException.assert_exception(expected_exception, actual_raised.value)

    async def test_ArtifactSinkFileSystem_WhenFolderNamesDifferOnlyByCase_ThenTheyCountAsTheSameFolder(self, tmp_path: Path) -> None:
        # Arrange - Windows and macOS file systems treat these as one folder
        shared_stem: str = create_random_label()
        first_work_item: WorkItem = create_random_work_item_with_stem(shared_stem, "pdf")
        second_work_item: WorkItem = create_random_work_item_with_stem(shared_stem.upper(), "pdf")
        artifact_sink_file_system: ArtifactSinkFileSystem = ArtifactSinkFileSystem(tmp_path)
        await artifact_sink_file_system(StepArtifact(PAGE_TEXT, b"first", first_work_item, StepPath((1,))))
        expected_exception: ExpectedException = ExpectedException(
            WorkItemFolderCollisionError, message_phrases=[first_work_item.id, second_work_item.id, "must be unique within a run"]
        )

        # Act
        with pytest.raises(WorkItemFolderCollisionError) as actual_raised:
            await artifact_sink_file_system(StepArtifact(PAGE_TEXT, b"second", second_work_item, StepPath((1,))))

        # Assert
        AsserterException.assert_exception(expected_exception, actual_raised.value)


@pytest.mark.acceptance
class TestAttachedRunLog:
    async def test_attached_run_log_WhenARunIsLogged_ThenTheLogSitsBesideTheArtifactsAndIsDetachedAfterwards(self, tmp_path: Path) -> None:
        # Arrange
        pipeline_name: str = create_random_pipeline_name()
        work_item: WorkItem = create_random_work_item()
        run_logger: logging.Logger = logging.getLogger("pipeline_breadcrumbs.acceptance_tests.hosting")
        run_logger.propagate = False
        expected_handler_count: int = len(run_logger.handlers)
        progress_message: str = "Loading pages"
        expected_run_log_rendered_text: ExpectedRenderedText = ExpectedRenderedText(
            contained_phrases=[
                "STEP 1: Load Pages - STARTED",
                f"{progress_message} (count=3)",
                f"Emitted artifact: {work_item.stem}_step_01_page_text.txt (5 B)",
            ]
        )
        expected_entry_names: list[str] = sorted([MANIFEST_FILENAME, RUN_LOG_FILENAME, work_item.stem])

        # Act
        with attached_run_log(run_logger, tmp_path, BreadcrumbFormatter(time_display=TimeDisplay.NONE)):
            pipeline_run: PipelineRun = PipelineRun(pipeline_name=pipeline_name, sink=ArtifactSinkFileSystem(tmp_path), logger=run_logger)
            async with pipeline_run, pipeline_run.open_work_item(work_item) as work_item_scope, work_item_scope.step(LOAD_PAGES) as step_scope:
                step_scope.info(progress_message, count=3)
                await step_scope.emit(PAGE_TEXT, b"hello")

        # Assert - the log sits beside the manifest and the work item's folder, and the handler is gone again
        AsserterRenderedText.assert_text(expected_run_log_rendered_text, _read_written_text(tmp_path / RUN_LOG_FILENAME))
        assert _list_entry_names(tmp_path) == expected_entry_names
        assert len(run_logger.handlers) == expected_handler_count
