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
from typing import Final, final, override

from pipeline_breadcrumbs import MANIFEST_KIND, Artifact, ArtifactSinkProtocol, RunArtifact, WorkItem
from pipeline_breadcrumbs.hosting import WorkItemFolderCollisionException, safe_path_component

_MANIFEST_BLOB_NAME: Final[str] = f"{MANIFEST_KIND.key}.{MANIFEST_KIND.extension}"
_RUN_CLAIMANT: Final[str] = "the run"


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
    case count as the same prefix. The run's own blobs sit beside the prefixes, so `manifest.json` and
    every run artifact's name are claimed for the run, and a work item whose prefix would take one of
    them raises too.
    """

    def __init__(self, run_blob_directory: Path) -> None:
        self._run_blob_directory: Path = run_blob_directory
        self._claimant_by_blob_name_key: dict[str, str] = {_blob_name_key(_MANIFEST_BLOB_NAME): _RUN_CLAIMANT}

    @override
    async def persist(self, artifact: Artifact) -> None:
        blob_path: Path = self._blob_path(artifact)
        await asyncio.to_thread(self._upload, blob_path, artifact.content)

    def _blob_path(self, artifact: Artifact) -> Path:
        if isinstance(artifact, RunArtifact):
            return self._run_blob_directory / self._claim_blob_name(safe_path_component(artifact.filename), _RUN_CLAIMANT)
        blob_prefix: str = self._claim_blob_name(safe_path_component(artifact.work_item.stem), _work_item_claimant(artifact.work_item))
        return self._run_blob_directory / blob_prefix / safe_path_component(artifact.filename)

    def _claim_blob_name(self, blob_name: str, claimant: str) -> str:
        owner: str = self._claimant_by_blob_name_key.setdefault(_blob_name_key(blob_name), claimant)
        if owner != claimant:
            raise WorkItemFolderCollisionException(
                f"Both {owner} and {claimant} map to the blob prefix '{blob_name}'; "
                "work item names must be unique within a run and must not take the run's own blob names"
            )
        return blob_name

    @staticmethod
    def _upload(blob_path: Path, content: bytes) -> None:
        blob_path.parent.mkdir(parents=True, exist_ok=True)
        blob_path.write_bytes(content)


def _work_item_claimant(work_item: WorkItem) -> str:
    return f"work item '{work_item.id}'"


def _blob_name_key(blob_name: str) -> str:
    # A file name can reach the same folder in composed or decomposed Unicode form (macOS file systems
    # store decomposed names), so the claim key is the NFC form, case-folded for case-insensitive folders.
    return unicodedata.normalize("NFC", blob_name).casefold()
