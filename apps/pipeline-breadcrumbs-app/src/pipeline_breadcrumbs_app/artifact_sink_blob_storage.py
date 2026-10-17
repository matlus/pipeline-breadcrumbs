"""A stand-in for blob storage: an artifact sink that uploads each artifact as a named blob.

A hosted application keeps its artifacts in a storage container, not on the machine that ran the
pipeline. This sink plays that side for the demo. The container is a folder, and a blob is a file
whose name is its path from the container root, the way a blob's name reads in a storage browser.
A real host implements `ArtifactSinkProtocol` with the storage SDK's container client in the same
place, and the system never knows which implementation it was handed.
"""

import asyncio
import unicodedata
from pathlib import Path
from typing import final, override

from pipeline_breadcrumbs import Artifact, ArtifactSinkProtocol, RunArtifact, WorkItem
from pipeline_breadcrumbs.hosting import WorkItemFolderCollisionException, safe_path_component


@final
class ArtifactSinkBlobStorage(ArtifactSinkProtocol):
    """Uploads each artifact as one blob, named `<run name>/<work item>/<filename>`.

    ```
    <container>/
      <run name>/manifest.json                        run-level blobs sit directly under the run
      <run name>/Contract 12/Contract 12_step_01_page_text_page_0000.txt
    ```

    A container holds many runs, so the run name leads every blob name. The application hands the sink
    the folder that stands for `<container>/<run name>/`; the sink owns uploading under it, which is
    state a bare function would have had to capture in a closure.

    Work item names must be unique within a run, because the blob prefix is named for the work item.
    Two items that map to the same prefix raise rather than overwrite each other's blobs, exactly as
    the file-system sink does. This stand-in writes to a local folder, so names that differ only by
    case count as the same prefix.
    """

    def __init__(self, run_blob_directory: Path) -> None:
        self._run_blob_directory: Path = run_blob_directory
        self._work_item_id_by_prefix: dict[str, str] = {}

    @override
    async def persist(self, artifact: Artifact) -> None:
        blob_path: Path = self._blob_path(artifact)
        await asyncio.to_thread(self._upload, blob_path, artifact.content)

    def _blob_path(self, artifact: Artifact) -> Path:
        if isinstance(artifact, RunArtifact):
            return self._run_blob_directory / safe_path_component(artifact.filename)
        return self._run_blob_directory / self._claim_prefix(artifact.work_item) / safe_path_component(artifact.filename)

    def _claim_prefix(self, work_item: WorkItem) -> str:
        blob_prefix: str = safe_path_component(work_item.stem)
        # A file name can reach the same folder in composed or decomposed Unicode form (macOS file systems
        # store decomposed names), so the claim key is the NFC form, case-folded for case-insensitive folders.
        owner_id: str = self._work_item_id_by_prefix.setdefault(unicodedata.normalize("NFC", blob_prefix).casefold(), work_item.id)
        if owner_id != work_item.id:
            raise WorkItemFolderCollisionException(
                f"Work items '{owner_id}' and '{work_item.id}' both map to the blob prefix '{blob_prefix}'; "
                "work item names must be unique within a run"
            )
        return blob_prefix

    @staticmethod
    def _upload(blob_path: Path, content: bytes) -> None:
        blob_path.parent.mkdir(parents=True, exist_ok=True)
        blob_path.write_bytes(content)
