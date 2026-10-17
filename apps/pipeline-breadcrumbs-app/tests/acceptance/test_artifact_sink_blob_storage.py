# Acceptance tests for the demo's blob-storage stand-in: work items that would share a blob prefix are
# refused instead of overwriting each other's blobs, the same guarantee the file-system sink gives.
# Black-box through `persist`, against a real temporary folder playing the container.

import secrets
from pathlib import Path
from typing import Final

import pytest
from breadcrumbs_acceptance_support.asserters.asserter_exception import AsserterException, ExpectedException

from pipeline_breadcrumbs import ArtifactKind, StepArtifact, StepPath, WorkItem
from pipeline_breadcrumbs.hosting import WorkItemFolderCollisionError
from pipeline_breadcrumbs_app.artifact_sink_blob_storage import ArtifactSinkBlobStorage

PAGE_TEXT: Final[ArtifactKind] = ArtifactKind("page_text", "txt", "text/plain")
_RANDOM_SUFFIX_BYTES: Final[int] = 4


def create_random_stem() -> str:
    return f"Contract {secrets.token_hex(_RANDOM_SUFFIX_BYTES)}"


def create_random_work_item_with_stem(stem: str, extension: str) -> WorkItem:
    return WorkItem(id=f"work-item-{secrets.token_hex(_RANDOM_SUFFIX_BYTES)}", name=f"{stem}.{extension}")


def create_random_run_name() -> str:
    return f"run-{secrets.token_hex(_RANDOM_SUFFIX_BYTES)}"


@pytest.mark.acceptance
class TestArtifactSinkBlobStorage:
    async def test_ArtifactSinkBlobStorage_WhenTwoWorkItemsShareABlobPrefix_ThenTheSecondIsRefusedInsteadOfOverwriting(self, tmp_path: Path) -> None:
        # Arrange
        shared_stem: str = create_random_stem()
        first_work_item: WorkItem = create_random_work_item_with_stem(shared_stem, "pdf")
        second_work_item: WorkItem = create_random_work_item_with_stem(shared_stem, "docx")
        artifact_sink_blob_storage: ArtifactSinkBlobStorage = ArtifactSinkBlobStorage(tmp_path / create_random_run_name())
        await artifact_sink_blob_storage.persist(StepArtifact(PAGE_TEXT, secrets.token_bytes(8), first_work_item, StepPath((1,))))
        expected_exception: ExpectedException = ExpectedException(
            WorkItemFolderCollisionError, message_phrases=[first_work_item.id, second_work_item.id, shared_stem, "must be unique within a run"]
        )

        # Act
        with pytest.raises(WorkItemFolderCollisionError) as actual_raised:
            await artifact_sink_blob_storage.persist(StepArtifact(PAGE_TEXT, secrets.token_bytes(8), second_work_item, StepPath((1,))))

        # Assert
        AsserterException.assert_exception(expected_exception, actual_raised.value)

    async def test_ArtifactSinkBlobStorage_WhenBlobPrefixesDifferOnlyByCase_ThenTheyCountAsTheSamePrefix(self, tmp_path: Path) -> None:
        # Arrange - the stand-in container is a local folder, and Windows and macOS treat these names as one
        shared_stem: str = create_random_stem()
        first_work_item: WorkItem = create_random_work_item_with_stem(shared_stem, "pdf")
        second_work_item: WorkItem = create_random_work_item_with_stem(shared_stem.upper(), "pdf")
        artifact_sink_blob_storage: ArtifactSinkBlobStorage = ArtifactSinkBlobStorage(tmp_path / create_random_run_name())
        await artifact_sink_blob_storage.persist(StepArtifact(PAGE_TEXT, secrets.token_bytes(8), first_work_item, StepPath((1,))))
        expected_exception: ExpectedException = ExpectedException(
            WorkItemFolderCollisionError, message_phrases=[first_work_item.id, second_work_item.id, "must be unique within a run"]
        )

        # Act
        with pytest.raises(WorkItemFolderCollisionError) as actual_raised:
            await artifact_sink_blob_storage.persist(StepArtifact(PAGE_TEXT, secrets.token_bytes(8), second_work_item, StepPath((1,))))

        # Assert
        AsserterException.assert_exception(expected_exception, actual_raised.value)
