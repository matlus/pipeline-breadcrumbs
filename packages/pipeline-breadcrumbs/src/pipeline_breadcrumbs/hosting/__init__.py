"""Host-side helpers: where artifacts and logs land on a local file system.

The core library knows no paths. Everything here is composition-root code; a production host
can replace it with an `ArtifactSinkProtocol` implementation for blob storage, and its own logging setup, without touching a step.
"""

from pipeline_breadcrumbs.hosting.file_system_artifact_sink import FileSystemArtifactSink
from pipeline_breadcrumbs.hosting.paths import safe_path_component
from pipeline_breadcrumbs.hosting.run_folder import create_run_folder
from pipeline_breadcrumbs.hosting.run_log import RUN_LOG_FILENAME, attached_run_log

__all__ = [
    "RUN_LOG_FILENAME",
    "FileSystemArtifactSink",
    "attached_run_log",
    "create_run_folder",
    "safe_path_component",
]
