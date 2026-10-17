"""A local-file-system artifact sink, for development and for hosts that keep artifacts on disk."""

import asyncio
import unicodedata
from pathlib import Path
from typing import final, override

from pipeline_breadcrumbs.artifacts import Artifact, ArtifactSinkProtocol, RunArtifact
from pipeline_breadcrumbs.path_components import safe_path_component
from pipeline_breadcrumbs.work_items import WorkItem


@final
class WorkItemFolderCollisionError(ValueError):
    """Two work items in one run map to the same folder, so the second would overwrite the first's artifacts."""


@final
class ArtifactSinkFileSystem(ArtifactSinkProtocol):
    """Writes each artifact under the run directory, in a folder per work item.

    ```
    <run directory>/
      manifest.json                         run-level artifacts sit at the top
      Contract 12/
        Contract 12_step_01_page_text_page_0000.txt
    ```

    A work item's files sit together in that one folder, never in subfolders by kind. Every
    filename carries its zero-padded step path right after the work item's name, so an
    ordinary alphabetical listing of the folder is the pipeline's step order. A subfolder per
    kind would split one step's files across folders and break that.

    Work item names must be unique within a run, because the folder is named for the work
    item. Two items that map to the same folder raise rather than overwrite each other. Names
    that differ only by case count as the same folder, because Windows and macOS file systems
    treat them that way. The sink remembers which work item claimed each folder; that
    registry is the one piece of state it keeps across calls.
    """

    def __init__(self, run_directory: Path) -> None:
        self._run_directory: Path = run_directory
        self._work_item_id_by_folder: dict[str, str] = {}

    @override
    async def persist(self, artifact: Artifact) -> None:
        target: Path = self._target_path(artifact)
        await asyncio.to_thread(self._write, target, artifact.content)

    def _target_path(self, artifact: Artifact) -> Path:
        if isinstance(artifact, RunArtifact):
            return self._run_directory / safe_path_component(artifact.filename)
        return self._run_directory / self._claim_folder(artifact.work_item) / safe_path_component(artifact.filename)

    def _claim_folder(self, work_item: WorkItem) -> str:
        folder_name: str = safe_path_component(work_item.stem)
        # A file name can reach the same folder in composed or decomposed Unicode form (macOS file systems
        # store decomposed names), so the claim key is the NFC form, case-folded for case-insensitive folders.
        owner_id: str = self._work_item_id_by_folder.setdefault(unicodedata.normalize("NFC", folder_name).casefold(), work_item.id)
        if owner_id != work_item.id:
            raise WorkItemFolderCollisionError(
                f"Work items '{owner_id}' and '{work_item.id}' both map to the folder '{folder_name}'; work item names must be unique within a run"
            )
        return folder_name

    @staticmethod
    def _write(target: Path, content: bytes) -> None:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
