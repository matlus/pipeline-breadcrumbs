# Acceptance tests for the host-side helpers that keep a run on disk: the file-system sink, the
# per-run folder and the attached run log. Black-box through their public classes and functions,
# against a real temporary folder.

import logging
from pathlib import Path
from typing import Final

import pytest
from breadcrumbs_acceptance_support.clock_testing import ClockTesting
from breadcrumbs_acceptance_support.data_generators import create_random_work_item

from pipeline_breadcrumbs import (
    ArtifactKind,
    ArtifactSinkProtocol,
    BreadcrumbFormatter,
    PipelineRun,
    RunArtifact,
    Step,
    StepArtifact,
    StepPath,
    TimeDisplay,
    WorkItem,
)
from pipeline_breadcrumbs.hosting import FileSystemArtifactSink, attached_run_log, create_run_folder, safe_path_component
from pipeline_breadcrumbs.testing import ArtifactRecorder

PAGE_IMAGE: Final[ArtifactKind] = ArtifactKind("page_image", "png", "image/png")
PAGE_TEXT: Final[ArtifactKind] = ArtifactKind("page_text", "txt", "text/plain")
MANIFEST: Final[ArtifactKind] = ArtifactKind("manifest", "json", "application/json")
LOAD_PAGES: Final[Step] = Step(1, "Load Pages")
READ_PAGES: Final[Step] = Step(2, "Read Pages")
MANIFEST_FILENAME: Final[str] = "manifest.json"


def _list_entry_names(actual_folder: Path) -> list[str]:
    return sorted(actual_entry.name for actual_entry in actual_folder.iterdir())


def _all_are_files(actual_folder: Path, actual_entry_names: list[str]) -> bool:
    return all((actual_folder / actual_entry_name).is_file() for actual_entry_name in actual_entry_names)


@pytest.mark.acceptance
class TestSafePathComponent:
    def test_safe_path_component_WhenTheNameHasUnsafeCharacters_ThenTheyAreReplaced(self) -> None:
        # Arrange / Act
        actual_component: str = safe_path_component("Q3: Plan / Draft?.pdf")

        # Assert
        expected_component: str = "Q3_ Plan _ Draft_.pdf"
        assert actual_component == expected_component

    def test_safe_path_component_WhenTheNameEndsWithDotsAndSpaces_ThenTheyAreTrimmed(self) -> None:
        # Arrange / Act / Assert - Windows refuses a trailing dot or space in a folder name
        assert safe_path_component("report. ") == "report"

    def test_safe_path_component_WhenNothingSafeRemains_ThenItStillNamesAFolder(self) -> None:
        # Arrange / Act / Assert
        assert safe_path_component("...") == "_"


@pytest.mark.acceptance
class TestRunFolder:
    def test_create_run_folder_WhenCreated_ThenTheNameIsTimestampThenLabel(self, tmp_path: Path, clock_testing: ClockTesting) -> None:
        # Arrange / Act
        actual_run_folder: Path = create_run_folder(tmp_path, "Contract 12", supplied_clock=clock_testing.clock)

        # Assert
        assert actual_run_folder.name == "20261003_140322_Contract 12"
        assert actual_run_folder.is_dir()

    def test_create_run_folder_WhenTwoRunsStartInTheSameSecond_ThenTheyDoNotCollide(self, tmp_path: Path, clock_testing: ClockTesting) -> None:
        # Arrange
        run_folder_label: str = "batch"

        # Act
        actual_first_folder: Path = create_run_folder(tmp_path, run_folder_label, supplied_clock=clock_testing.clock)
        actual_second_folder: Path = create_run_folder(tmp_path, run_folder_label, supplied_clock=clock_testing.clock)

        # Assert
        assert (actual_first_folder.name, actual_second_folder.name) == ("20261003_140322_batch", "20261003_140322_batch_2")

    def test_create_run_folder_WhenTheSameFileIsRunLater_ThenTheEarlierRunIsKept(self, tmp_path: Path, clock_testing: ClockTesting) -> None:
        # Arrange
        run_folder_label: str = "Contract 12"
        actual_first_folder: Path = create_run_folder(tmp_path, run_folder_label, supplied_clock=clock_testing.clock)
        clock_testing.advance(60)

        # Act
        actual_second_folder: Path = create_run_folder(tmp_path, run_folder_label, supplied_clock=clock_testing.clock)

        # Assert
        assert sorted(actual_path.name for actual_path in tmp_path.iterdir()) == [actual_first_folder.name, actual_second_folder.name]


@pytest.mark.acceptance
class TestFileSystemArtifactSink:
    async def test_FileSystemArtifactSink_WhenAStepArtifactArrives_ThenItLandsInItsWorkItemsFolder(self, tmp_path: Path) -> None:
        # Arrange
        work_item: WorkItem = WorkItem("1", "Contract 12.pdf")
        file_system_artifact_sink: FileSystemArtifactSink = FileSystemArtifactSink(tmp_path)

        # Act
        await file_system_artifact_sink.persist(StepArtifact(PAGE_TEXT, b"hello", work_item, StepPath((1,)), discriminator="page_0000"))

        # Assert
        actual_written_content: bytes = (tmp_path / "Contract 12" / "Contract 12_step_01_page_text_page_0000.txt").read_bytes()
        assert actual_written_content == b"hello"

    async def test_FileSystemArtifactSink_WhenARunArtifactArrives_ThenItSitsAtTheTop(self, tmp_path: Path) -> None:
        # Arrange
        file_system_artifact_sink: FileSystemArtifactSink = FileSystemArtifactSink(tmp_path)

        # Act
        await file_system_artifact_sink.persist(RunArtifact(MANIFEST, b"{}"))

        # Assert
        assert (tmp_path / "manifest.json").read_bytes() == b"{}"

    async def test_FileSystemArtifactSink_WhenOneWorkItemHasManyKindsOfArtifact_ThenTheyShareOneFolderThatListsInStepOrder(
        self, tmp_path: Path
    ) -> None:
        # Arrange - the artifacts arrive in an order unrelated to their steps
        work_item: WorkItem = WorkItem("1", "Contract 12.pdf")
        file_system_artifact_sink: FileSystemArtifactSink = FileSystemArtifactSink(tmp_path)

        # Act
        await file_system_artifact_sink.persist(StepArtifact(PAGE_TEXT, b"c", work_item, StepPath((10,))))
        await file_system_artifact_sink.persist(StepArtifact(PAGE_IMAGE, b"a", work_item, StepPath((2, 9))))
        await file_system_artifact_sink.persist(StepArtifact(PAGE_TEXT, b"b", work_item, StepPath((2, 10))))
        await file_system_artifact_sink.persist(StepArtifact(PAGE_IMAGE, b"d", work_item, StepPath((1,))))

        # Assert - one folder, no subfolders, and an alphabetical listing is the step order
        actual_work_item_folder: Path = tmp_path / "Contract 12"
        actual_entry_names: list[str] = _list_entry_names(actual_work_item_folder)
        expected_entry_names: list[str] = [
            "Contract 12_step_01_page_image.png",
            "Contract 12_step_02.09_page_image.png",
            "Contract 12_step_02.10_page_text.txt",
            "Contract 12_step_10_page_text.txt",
        ]
        assert actual_entry_names == expected_entry_names
        assert _all_are_files(actual_work_item_folder, actual_entry_names)

    async def test_FileSystemArtifactSink_WhenTwoWorkItemsShareAFolderName_ThenTheSecondIsRefusedInsteadOfOverwriting(self, tmp_path: Path) -> None:
        # Arrange
        file_system_artifact_sink: FileSystemArtifactSink = FileSystemArtifactSink(tmp_path)
        await file_system_artifact_sink.persist(StepArtifact(PAGE_TEXT, b"first", WorkItem("1", "Contract 12.pdf"), StepPath((1,))))

        # Act / Assert
        with pytest.raises(ValueError, match="must be unique within a run"):
            await file_system_artifact_sink.persist(StepArtifact(PAGE_TEXT, b"second", WorkItem("2", "Contract 12.docx"), StepPath((1,))))

    async def test_FileSystemArtifactSink_WhenFolderNamesDifferOnlyByCase_ThenTheyCountAsTheSameFolder(self, tmp_path: Path) -> None:
        # Arrange - Windows and macOS file systems treat these as one folder
        file_system_artifact_sink: FileSystemArtifactSink = FileSystemArtifactSink(tmp_path)
        await file_system_artifact_sink.persist(StepArtifact(PAGE_TEXT, b"first", WorkItem("1", "Contract 12.pdf"), StepPath((1,))))

        # Act / Assert
        with pytest.raises(ValueError, match="must be unique within a run"):
            await file_system_artifact_sink.persist(StepArtifact(PAGE_TEXT, b"second", WorkItem("2", "CONTRACT 12.pdf"), StepPath((1,))))


@pytest.mark.acceptance
class TestAttachedRunLog:
    async def test_attached_run_log_WhenARunIsLogged_ThenTheLogSitsBesideTheArtifactsAndIsDetachedAfterwards(self, tmp_path: Path) -> None:
        # Arrange
        work_item: WorkItem = create_random_work_item()
        run_logger: logging.Logger = logging.getLogger("pipeline_breadcrumbs.acceptance_tests.hosting")
        run_logger.propagate = False
        expected_handler_count: int = len(run_logger.handlers)

        # Act
        with attached_run_log(run_logger, tmp_path, BreadcrumbFormatter(time_display=TimeDisplay.NONE)):
            pipeline_run: PipelineRun = PipelineRun(pipeline_name="demo", artifact_sink=FileSystemArtifactSink(tmp_path), logger=run_logger)
            async with pipeline_run, pipeline_run.open_work_item(work_item) as work_item_scope, work_item_scope.step(LOAD_PAGES) as step_scope:
                step_scope.info("Loading pages", count=3)
                await step_scope.emit(PAGE_TEXT, b"hello")

        # Assert
        actual_run_log: str = (tmp_path / "run.log").read_text(encoding="utf-8")
        assert "STEP 1: Load Pages - STARTED" in actual_run_log
        assert "Loading pages (count=3)" in actual_run_log
        assert f"Emitted artifact: {work_item.stem}_step_01_page_text.txt (5 B)" in actual_run_log
        assert len(run_logger.handlers) == expected_handler_count
        assert (tmp_path / "manifest.json").exists()


async def _run_two_steps_into(artifact_sink: ArtifactSinkProtocol, work_item: WorkItem, run_logger: logging.Logger) -> None:
    pipeline_run: PipelineRun = PipelineRun(pipeline_name="demo", artifact_sink=artifact_sink, logger=run_logger)
    async with pipeline_run, pipeline_run.open_work_item(work_item) as work_item_scope:
        async with work_item_scope.step(LOAD_PAGES) as load_scope:
            await load_scope.emit(PAGE_TEXT, b"page one", discriminator="page_0000")
        async with work_item_scope.step(READ_PAGES) as read_scope:
            await read_scope.emit(PAGE_IMAGE, b"image", discriminator="page_0000")
            await read_scope.emit(PAGE_TEXT, b"page two", discriminator="page_0001")


@pytest.mark.acceptance
class TestArtifactSinkSwapping:
    async def test_PipelineRun_WhenTheSameRunUsesTheFileSystemSinkOrTheRecorder_ThenTheArtifactFilenamesAreTheSameInTheSameOrder(
        self, tmp_path: Path, run_logger: logging.Logger
    ) -> None:
        # Arrange
        work_item: WorkItem = create_random_work_item()
        artifact_recorder: ArtifactRecorder = ArtifactRecorder()

        # Act
        await _run_two_steps_into(FileSystemArtifactSink(tmp_path), work_item, run_logger)
        await _run_two_steps_into(artifact_recorder, work_item, run_logger)

        # Assert - a work item's folder lists alphabetically in step order, which is also the order the recorder received them
        actual_recorded_step_filenames: list[str] = [
            actual_filename for actual_filename in artifact_recorder.filenames() if actual_filename != MANIFEST_FILENAME
        ]
        actual_file_system_step_filenames: list[str] = _list_entry_names(tmp_path / safe_path_component(work_item.stem))
        assert actual_file_system_step_filenames == actual_recorded_step_filenames
        assert len(actual_recorded_step_filenames) == 3
        assert (tmp_path / MANIFEST_FILENAME).exists()
        assert artifact_recorder.filenames()[-1] == MANIFEST_FILENAME
