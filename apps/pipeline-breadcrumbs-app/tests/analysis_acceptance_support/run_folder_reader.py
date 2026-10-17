import json
from pathlib import Path
from typing import Final

from breadcrumbs_acceptance_support.manifest_documents import ManifestDocument, parse_manifest_document

from pipeline_breadcrumbs_app.telemetry import TELEMETRY_FILENAME, ExceptionTelemetry

_MANIFEST_FILENAME: Final[str] = "manifest.json"
_RUN_LOG_FILENAME: Final[str] = "run.log"


class RunFolderReader:
    """Gathers what a demo run left on disk, so a test reads its observations after Act and its asserters only compare."""

    @staticmethod
    def read_manifest(run_directory: Path) -> ManifestDocument:
        return parse_manifest_document((run_directory / _MANIFEST_FILENAME).read_text(encoding="utf-8"))

    @staticmethod
    def read_run_log(run_directory: Path) -> str:
        return (run_directory / _RUN_LOG_FILENAME).read_text(encoding="utf-8")

    @staticmethod
    def read_exception_telemetry(run_directory: Path) -> list[ExceptionTelemetry]:
        """The exceptions telemetry received, one per line; none if nothing was ever sent."""
        telemetry_path: Path = run_directory / TELEMETRY_FILENAME
        if not telemetry_path.exists():
            return []
        return [ExceptionTelemetry(**json.loads(telemetry_line)) for telemetry_line in telemetry_path.read_text(encoding="utf-8").splitlines()]

    @staticmethod
    def list_entry_names(folder: Path) -> list[str]:
        return sorted(entry.name for entry in folder.iterdir())

    @staticmethod
    def list_folder_names(folder: Path) -> list[str]:
        return sorted(entry.name for entry in folder.iterdir() if entry.is_dir())

    @staticmethod
    def list_blob_names(container: Path) -> list[str]:
        """Every blob in a container folder, named by its path from the container root with forward slashes."""
        return sorted(entry.relative_to(container).as_posix() for entry in container.rglob("*") if entry.is_file())

    @staticmethod
    def read_text_by_filename(folder: Path) -> dict[str, str]:
        return {entry.name: entry.read_text(encoding="utf-8") for entry in sorted(folder.iterdir()) if entry.is_file()}
