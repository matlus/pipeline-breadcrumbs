"""Host-side helpers: where artifacts and logs land on a local file system.

The core library knows no paths. Everything here is composition-root code; a production host
can replace it with an `ArtifactSinkProtocol` implementation for blob storage, and its own logging setup, without touching a step.
"""

from pipeline_breadcrumbs.hosting.artifact_sink_file_system import ArtifactSinkFileSystem, WorkItemFolderCollisionException
from pipeline_breadcrumbs.hosting.run_folder import create_run_folder
from pipeline_breadcrumbs.hosting.run_log import RUN_LOG_FILENAME, attached_run_log
from pipeline_breadcrumbs.path_components import safe_path_component

__all__ = [
    "RUN_LOG_FILENAME",
    "ArtifactSinkFileSystem",
    "WorkItemFolderCollisionException",
    "attached_run_log",
    "create_run_folder",
    "safe_path_component",
]
