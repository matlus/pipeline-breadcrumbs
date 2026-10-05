"""A stand-in for blob storage: an artifact sink that uploads each artifact as a named blob.

A hosted application keeps its artifacts in a storage container, not on the machine that ran the
pipeline. This sink plays that side for the demo. The container is a folder, and a blob is a file
whose name is its path from the container root, the way a blob's name reads in a storage browser.
A real host implements `ArtifactSinkProtocol` with the storage SDK's container client in the same
place, and the system never knows which implementation it was handed.
"""

import asyncio
from pathlib import Path
from typing import final, override

from pipeline_breadcrumbs import Artifact, ArtifactSinkProtocol, RunArtifact
from pipeline_breadcrumbs.hosting import safe_path_component


@final
class BlobStorageArtifactSink(ArtifactSinkProtocol):
    """Uploads each artifact as one blob, named `<run name>/<work item>/<filename>`.

    ```
    <container>/
      <run name>/manifest.json                        run-level blobs sit directly under the run
      <run name>/Contract 12/Contract 12_step_01_page_text_page_0000.txt
    ```

    A container holds many runs, so the run name leads every blob name. The sink owns the container
    it uploads to, which is state a bare function would have had to capture in a closure.
    """

    def __init__(self, container_directory: Path, run_name: str) -> None:
        self._container_directory: Path = container_directory
        self._run_name: str = safe_path_component(run_name)

    @property
    def run_directory(self) -> Path:
        """Where this run's blobs land inside the container."""
        return self._container_directory / self._run_name

    @override
    async def persist(self, artifact: Artifact) -> None:
        blob_path: Path = self._blob_path(artifact)
        await asyncio.to_thread(self._upload, blob_path, artifact.content)

    def _blob_path(self, artifact: Artifact) -> Path:
        if isinstance(artifact, RunArtifact):
            return self.run_directory / safe_path_component(artifact.filename)
        return self.run_directory / safe_path_component(artifact.work_item.stem) / safe_path_component(artifact.filename)

    @staticmethod
    def _upload(blob_path: Path, content: bytes) -> None:
        blob_path.parent.mkdir(parents=True, exist_ok=True)
        blob_path.write_bytes(content)
