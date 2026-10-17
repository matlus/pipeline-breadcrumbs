"""A local-file-system artifact sink, for development and for hosts that keep artifacts on disk."""

import asyncio
import unicodedata
from pathlib import Path
from typing import Final, final, override

from pipeline_breadcrumbs.artifacts import Artifact, ArtifactSinkProtocol, RunArtifact
from pipeline_breadcrumbs.exceptions import PipelineBreadcrumbsBusinessBaseException
from pipeline_breadcrumbs.hosting.run_log import RUN_LOG_FILENAME
from pipeline_breadcrumbs.manifest import MANIFEST_FILENAME
from pipeline_breadcrumbs.path_components import safe_path_component
from pipeline_breadcrumbs.work_items import WorkItem

_RUN_CLAIMANT: Final[str] = "the run"


@final
class WorkItemFolderCollisionException(PipelineBreadcrumbsBusinessBaseException):
    """Two work items in one run map to the same folder, or one maps to a name the run keeps for itself, such as
    `manifest.json`, so one would overwrite the other's artifacts.

    The work items' names come from the caller, who can correct them, so it is a business exception.
    """


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
    treat them that way. The run's own entries share the top level, so `manifest.json`,
    `run.log` and every run artifact's filename are claimed for the run, and a work item
    whose folder would take one of them raises too. The sink remembers who claimed each
    top-level entry; that registry is the one piece of state it keeps across calls.
    """

    def __init__(self, run_directory: Path) -> None:
        self._run_directory: Path = run_directory
        self._claimant_by_entry_key: dict[str, str] = {
            _entry_key(MANIFEST_FILENAME): _RUN_CLAIMANT,
            _entry_key(RUN_LOG_FILENAME): _RUN_CLAIMANT,
        }

    @override
    async def persist(self, artifact: Artifact) -> None:
        target: Path = self._target_path(artifact)
        await asyncio.to_thread(self._write, target, artifact.content)

    def _target_path(self, artifact: Artifact) -> Path:
        if isinstance(artifact, RunArtifact):
            return self._run_directory / self._claim_entry(safe_path_component(artifact.filename), _RUN_CLAIMANT)
        folder_name: str = self._claim_entry(safe_path_component(artifact.work_item.stem), _work_item_claimant(artifact.work_item))
        return self._run_directory / folder_name / safe_path_component(artifact.filename)

    def _claim_entry(self, entry_name: str, claimant: str) -> str:
        owner: str = self._claimant_by_entry_key.setdefault(_entry_key(entry_name), claimant)
        if owner != claimant:
            raise WorkItemFolderCollisionException(
                f"Both {owner} and {claimant} map to the entry '{entry_name}' in the run directory; "
                "work item names must be unique within a run and must not take the run's own entry names"
            )
        return entry_name

    @staticmethod
    def _write(target: Path, content: bytes) -> None:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)


def _work_item_claimant(work_item: WorkItem) -> str:
    return f"work item '{work_item.id}'"


def _entry_key(entry_name: str) -> str:
    # A file name can reach the same entry in composed or decomposed Unicode form (macOS file systems
    # store decomposed names), so the claim key is the NFC form, case-folded for case-insensitive folders.
    return unicodedata.normalize("NFC", entry_name).casefold()
