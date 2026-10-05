import json
import re
from collections.abc import Mapping
from pathlib import Path
from typing import Any


class AsserterRunFolder:
    """Reads the folder a demo run left behind, the way an engineer investigating it would."""

    @staticmethod
    def read_manifest(actual_run_directory: Path) -> dict[str, Any]:
        actual_manifest: dict[str, Any] = json.loads((actual_run_directory / "manifest.json").read_text(encoding="utf-8"))
        return actual_manifest

    @staticmethod
    def assert_exactly_these_entries(expected_entry_names: set[str], actual_folder: Path) -> None:
        actual_entry_names: set[str] = {actual_entry.name for actual_entry in actual_folder.iterdir()}
        assert expected_entry_names == actual_entry_names, (
            f"RUN FOLDER ASSERTION FAILED\nexpected: {sorted(expected_entry_names)}\nactual:   {sorted(actual_entry_names)}"
        )

    @staticmethod
    def assert_step_statuses(
        expected_step_status_by_path: Mapping[str, str],
        work_item_name: str,
        actual_manifest: Mapping[str, Any],
    ) -> None:
        actual_work_item: Mapping[str, Any] = AsserterRunFolder.find_work_item(work_item_name, actual_manifest)
        actual_step_status_by_path: dict[str, str] = {
            actual_step["step_path"]: actual_step["step_status"] for actual_step in actual_work_item["step_records"]
        }
        expected_step_statuses: dict[str, str] = dict(expected_step_status_by_path)
        assert expected_step_statuses == actual_step_status_by_path, (
            f"STEP STATUS ASSERTION FAILED for '{work_item_name}'\nexpected: {expected_step_statuses}\nactual:   {actual_step_status_by_path}"
        )

    @staticmethod
    def list_entry_names(actual_folder: Path) -> list[str]:
        return sorted(actual_entry.name for actual_entry in actual_folder.iterdir())

    @staticmethod
    def read_step_paths_from_filenames(actual_filenames: list[str]) -> list[tuple[int, ...]]:
        """The step path each filename carries after its work item name, such as `_step_03.02_` read as (3, 2)."""
        actual_step_paths: list[tuple[int, ...]] = []
        for actual_filename in actual_filenames:
            step_path_match: re.Match[str] | None = re.search(r"_step_(\d\d(?:\.\d\d)*)_", actual_filename)
            if step_path_match is not None:
                actual_step_paths.append(tuple(int(step_number) for step_number in step_path_match.group(1).split(".")))
        return actual_step_paths

    @staticmethod
    def all_are_files(actual_folder: Path, actual_entry_names: list[str]) -> bool:
        return all((actual_folder / actual_entry_name).is_file() for actual_entry_name in actual_entry_names)

    @staticmethod
    def read_telemetry(actual_run_directory: Path) -> list[dict[str, Any]]:
        """The exceptions telemetry received, one per line; none if nothing was ever sent."""
        actual_telemetry_path: Path = actual_run_directory / "telemetry.jsonl"
        if not actual_telemetry_path.exists():
            return []
        return [json.loads(actual_line) for actual_line in actual_telemetry_path.read_text(encoding="utf-8").splitlines()]

    @staticmethod
    def find_work_item(work_item_name: str, actual_manifest: Mapping[str, Any]) -> dict[str, Any]:
        return next(
            actual_work_item for actual_work_item in actual_manifest["work_item_records"] if actual_work_item["work_item_name"] == work_item_name
        )
