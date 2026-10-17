import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Final

_MANIFEST_FILENAME: Final[str] = "manifest.json"
_TELEMETRY_FILENAME: Final[str] = "telemetry.jsonl"
_TRACEBACK_HEADER: Final[str] = "Traceback (most recent call last)"
_STEP_PATH_PATTERN: Final[re.Pattern[str]] = re.compile(r"_step_(\d\d(?:\.\d\d)*)_")


@dataclass(frozen=True)
class ExpectedWorkItemOutcome:
    name: str
    work_item_status: str
    step_status_by_path: Mapping[str, str]
    failure_phrase: str | None = None
    present_artifact_fragments: Sequence[str] = field(default_factory=tuple[str, ...])
    absent_artifact_fragments: Sequence[str] = field(default_factory=tuple[str, ...])


@dataclass(frozen=True)
class ExpectedRunOutcome:
    pipeline_name: str
    run_status: str
    failed_work_item_names: Sequence[str]
    work_item_outcomes: Sequence[ExpectedWorkItemOutcome]


@dataclass(frozen=True)
class ExpectedExceptionTelemetry:
    severity: str
    exception_type: str
    stack_trace_phrase: str
    custom_dimensions: Mapping[str, object]


class AsserterRunFolder:
    """Reads the folder a demo run left behind, the way an engineer investigating it would, and reports every difference at once."""

    @staticmethod
    def assert_run_outcome(
        expected_run_outcome: ExpectedRunOutcome, actual_failed_work_item_names: Sequence[str], actual_run_directory: Path
    ) -> None:
        assertion_failures: list[str] = []
        actual_manifest: dict[str, Any] = AsserterRunFolder._read_manifest(actual_run_directory)
        if list(actual_failed_work_item_names) != list(expected_run_outcome.failed_work_item_names):
            assertion_failures.append(
                f"failed work items: expected {list(expected_run_outcome.failed_work_item_names)} but found {list(actual_failed_work_item_names)}"
            )
        if actual_manifest["pipeline_name"] != expected_run_outcome.pipeline_name:
            assertion_failures.append(
                f"pipeline name: expected {expected_run_outcome.pipeline_name!r} but found {actual_manifest['pipeline_name']!r}"
            )
        if actual_manifest["run_status"] != expected_run_outcome.run_status:
            assertion_failures.append(f"run status: expected {expected_run_outcome.run_status!r} but found {actual_manifest['run_status']!r}")
        for expected_work_item_outcome in expected_run_outcome.work_item_outcomes:
            AsserterRunFolder._compare_work_item(expected_work_item_outcome, actual_manifest, assertion_failures)
        assert not assertion_failures, "RUN OUTCOME ASSERTION FAILED\n" + "\n".join(assertion_failures)

    @staticmethod
    def assert_exactly_these_entries(expected_entry_names: set[str], actual_folder: Path) -> None:
        actual_entry_names: set[str] = {actual_entry.name for actual_entry in actual_folder.iterdir()}
        assert expected_entry_names == actual_entry_names, (
            f"RUN FOLDER ASSERTION FAILED\nexpected: {sorted(expected_entry_names)}\nactual:   {sorted(actual_entry_names)}"
        )

    @staticmethod
    def assert_work_item_files(expected_file_start_by_filename: Mapping[str, str], actual_work_item_folder: Path) -> None:
        """Each named file exists in the work item's folder and starts with the given text (empty text checks existence only)."""
        assertion_failures: list[str] = []
        for expected_filename, expected_start in expected_file_start_by_filename.items():
            actual_path: Path = actual_work_item_folder / expected_filename
            if not actual_path.is_file():
                assertion_failures.append(f"{expected_filename}: missing")
            elif not actual_path.read_text(encoding="utf-8").startswith(expected_start):
                assertion_failures.append(f"{expected_filename}: expected it to start with {expected_start!r}")
        assert not assertion_failures, "WORK ITEM FILES ASSERTION FAILED\n" + "\n".join(assertion_failures)

    @staticmethod
    def assert_listing_in_step_order(expected_first_step_path: tuple[int, ...], actual_work_item_folder: Path) -> None:
        assertion_failures: list[str] = []
        actual_listing: list[str] = sorted(actual_entry.name for actual_entry in actual_work_item_folder.iterdir())
        actual_step_paths: list[tuple[int, ...]] = AsserterRunFolder._read_step_paths(actual_listing)
        if len(actual_step_paths) != len(actual_listing):
            assertion_failures.append(f"every entry should carry a step path; {len(actual_listing) - len(actual_step_paths)} do not")
        if actual_step_paths != sorted(actual_step_paths):
            assertion_failures.append(f"step paths go backwards in an alphabetical listing: {actual_step_paths}")
        if not actual_step_paths or actual_step_paths[0] != expected_first_step_path:
            assertion_failures.append(f"the listing should start at step {expected_first_step_path}")
        actual_folder_names: list[str] = [actual_name for actual_name in actual_listing if (actual_work_item_folder / actual_name).is_dir()]
        if actual_folder_names:
            assertion_failures.append(f"a work item folder holds only files, but found folders {actual_folder_names}")
        assert not assertion_failures, "STEP ORDER ASSERTION FAILED\n" + "\n".join(assertion_failures)

    @staticmethod
    def assert_raw_replies(
        expected_raw_reply_filenames: Sequence[str], expected_reply_start_by_filename: Mapping[str, str], actual_work_item_folder: Path
    ) -> None:
        assertion_failures: list[str] = []
        actual_raw_reply_filenames: list[str] = sorted(
            actual_entry.name for actual_entry in actual_work_item_folder.iterdir() if "raw_detection_response" in actual_entry.name
        )
        if actual_raw_reply_filenames != list(expected_raw_reply_filenames):
            assertion_failures.append(f"raw replies: expected {list(expected_raw_reply_filenames)} but found {actual_raw_reply_filenames}")
        for expected_filename, expected_start in expected_reply_start_by_filename.items():
            actual_path: Path = actual_work_item_folder / expected_filename
            if not actual_path.is_file() or not actual_path.read_text(encoding="utf-8").startswith(expected_start):
                assertion_failures.append(f"{expected_filename}: expected a reply starting with {expected_start!r}")
        assert not assertion_failures, "RAW REPLIES ASSERTION FAILED\n" + "\n".join(assertion_failures)

    @staticmethod
    def assert_distinct_run_folders(expected_manifest_filename: str, actual_first_run_directory: Path, actual_second_run_directory: Path) -> None:
        assertion_failures: list[str] = []
        if actual_first_run_directory == actual_second_run_directory:
            assertion_failures.append(f"both runs wrote to {actual_first_run_directory}")
        assertion_failures.extend(
            f"{actual_run_directory} has no {expected_manifest_filename}"
            for actual_run_directory in (actual_first_run_directory, actual_second_run_directory)
            if not (actual_run_directory / expected_manifest_filename).is_file()
        )
        assert not assertion_failures, "DISTINCT RUN FOLDERS ASSERTION FAILED\n" + "\n".join(assertion_failures)

    @staticmethod
    def assert_same_work_item_listings(
        expected_work_item_folder_names: Sequence[str], actual_local_run_directory: Path, actual_hosted_run_directory: Path
    ) -> None:
        assertion_failures: list[str] = []
        for expected_folder_name in expected_work_item_folder_names:
            actual_local_listing: list[str] = sorted(
                actual_entry.name for actual_entry in (actual_local_run_directory / expected_folder_name).iterdir()
            )
            actual_hosted_listing: list[str] = sorted(
                actual_entry.name for actual_entry in (actual_hosted_run_directory / expected_folder_name).iterdir()
            )
            if actual_hosted_listing != actual_local_listing:
                assertion_failures.append(f"{expected_folder_name}:\n  local  {actual_local_listing}\n  hosted {actual_hosted_listing}")
        assert not assertion_failures, "WORK ITEM LISTINGS ASSERTION FAILED\n" + "\n".join(assertion_failures)

    @staticmethod
    def assert_failure_logged_once(expected_host_log_line: str, expected_facts: Sequence[str], actual_run_directory: Path) -> None:
        """The application logs the exception once, its traceback after its own line, with every named fact; steps print no traceback."""
        assertion_failures: list[str] = []
        actual_run_log: str = (actual_run_directory / "run.log").read_text(encoding="utf-8")
        actual_host_line_count: int = actual_run_log.count(expected_host_log_line)
        if actual_host_line_count != 1:
            assertion_failures.append(f"expected {expected_host_log_line!r} once but found it {actual_host_line_count} time(s)")
        elif _TRACEBACK_HEADER not in actual_run_log or actual_run_log.index(_TRACEBACK_HEADER) < actual_run_log.index(expected_host_log_line):
            assertion_failures.append("the first traceback should follow the application's own line, not a step breadcrumb")
        assertion_failures.extend(f"missing fact {expected_fact!r}" for expected_fact in expected_facts if expected_fact not in actual_run_log)
        assert not assertion_failures, "FAILURE LOG ASSERTION FAILED\n" + "\n".join(assertion_failures)

    @staticmethod
    def assert_single_exception_telemetry(expected_exception_telemetry: ExpectedExceptionTelemetry, actual_run_directory: Path) -> None:
        """Exactly one exception reached telemetry, with its facts and the run's own identity from the manifest."""
        assertion_failures: list[str] = []
        actual_telemetry: list[dict[str, Any]] = AsserterRunFolder.read_telemetry(actual_run_directory)
        # A prerequisite: the other comparisons describe that one exception, so without exactly one there is nothing to compare.
        assert len(actual_telemetry) == 1, f"TELEMETRY ASSERTION FAILED\nexpected one exception but telemetry received {len(actual_telemetry)}"
        actual_exception_telemetry: dict[str, Any] = actual_telemetry[0]
        if actual_exception_telemetry["severity"] != expected_exception_telemetry.severity:
            assertion_failures.append(
                f"severity: expected {expected_exception_telemetry.severity!r} but found {actual_exception_telemetry['severity']!r}"
            )
        if actual_exception_telemetry["exception_type"] != expected_exception_telemetry.exception_type:
            assertion_failures.append(
                f"exception type: expected {expected_exception_telemetry.exception_type!r} but found {actual_exception_telemetry['exception_type']!r}"
            )
        if expected_exception_telemetry.stack_trace_phrase not in (actual_exception_telemetry["stack_trace"] or ""):
            assertion_failures.append(f"stack trace: expected the phrase {expected_exception_telemetry.stack_trace_phrase!r}")
        actual_custom_dimensions: dict[str, Any] = actual_exception_telemetry["custom_dimensions"]
        expected_custom_dimensions: dict[str, object] = {
            **expected_exception_telemetry.custom_dimensions,
            "pipeline.run.id": AsserterRunFolder._read_manifest(actual_run_directory)["run_id"],
        }
        assertion_failures.extend(
            f"custom dimension {expected_name!r}: expected {expected_value!r} but found {actual_custom_dimensions.get(expected_name)!r}"
            for expected_name, expected_value in expected_custom_dimensions.items()
            if actual_custom_dimensions.get(expected_name) != expected_value
        )
        assert not assertion_failures, "TELEMETRY ASSERTION FAILED\n" + "\n".join(assertion_failures)

    @staticmethod
    def list_entry_names(actual_folder: Path) -> list[str]:
        return sorted(actual_entry.name for actual_entry in actual_folder.iterdir())

    @staticmethod
    def read_telemetry(actual_run_directory: Path) -> list[dict[str, Any]]:
        """The exceptions telemetry received, one per line; none if nothing was ever sent."""
        actual_telemetry_path: Path = actual_run_directory / _TELEMETRY_FILENAME
        if not actual_telemetry_path.exists():
            return []
        return [json.loads(actual_line) for actual_line in actual_telemetry_path.read_text(encoding="utf-8").splitlines()]

    @staticmethod
    def _compare_work_item(
        expected_work_item_outcome: ExpectedWorkItemOutcome, actual_manifest: Mapping[str, Any], assertion_failures: list[str]
    ) -> None:
        actual_work_items: list[dict[str, Any]] = [
            actual_work_item
            for actual_work_item in actual_manifest["work_item_records"]
            if actual_work_item["work_item_name"] == expected_work_item_outcome.name
        ]
        if len(actual_work_items) != 1:
            assertion_failures.append(f"'{expected_work_item_outcome.name}': expected one record but found {len(actual_work_items)}")
            return
        actual_work_item: dict[str, Any] = actual_work_items[0]
        work_item_label: str = f"'{expected_work_item_outcome.name}'"
        actual_work_item_status: str = actual_work_item["work_item_status"]
        if actual_work_item_status != expected_work_item_outcome.work_item_status:
            assertion_failures.append(
                f"{work_item_label} status: expected {expected_work_item_outcome.work_item_status!r} but found {actual_work_item_status!r}"
            )
        actual_step_status_by_path: dict[str, str] = {
            actual_step["step_path"]: actual_step["step_status"] for actual_step in actual_work_item["step_records"]
        }
        if actual_step_status_by_path != dict(expected_work_item_outcome.step_status_by_path):
            assertion_failures.append(
                f"{work_item_label} steps: expected {dict(expected_work_item_outcome.step_status_by_path)} but found {actual_step_status_by_path}"
            )
        if expected_work_item_outcome.failure_phrase is not None and expected_work_item_outcome.failure_phrase not in (
            actual_work_item["failure"] or ""
        ):
            assertion_failures.append(f"{work_item_label} failure: expected the phrase {expected_work_item_outcome.failure_phrase!r}")
        actual_artifact_filenames: list[str] = [actual_artifact["filename"] for actual_artifact in actual_work_item["artifact_records"]]
        assertion_failures.extend(
            f"{work_item_label}: expected an artifact named with {expected_fragment!r}"
            for expected_fragment in expected_work_item_outcome.present_artifact_fragments
            if not any(expected_fragment in actual_filename for actual_filename in actual_artifact_filenames)
        )
        assertion_failures.extend(
            f"{work_item_label}: expected no artifact named with {expected_fragment!r}"
            for expected_fragment in expected_work_item_outcome.absent_artifact_fragments
            if any(expected_fragment in actual_filename for actual_filename in actual_artifact_filenames)
        )

    @staticmethod
    def _read_manifest(actual_run_directory: Path) -> dict[str, Any]:
        actual_manifest: dict[str, Any] = json.loads((actual_run_directory / _MANIFEST_FILENAME).read_text(encoding="utf-8"))
        return actual_manifest

    @staticmethod
    def _read_step_paths(actual_filenames: list[str]) -> list[tuple[int, ...]]:
        """The step path each filename carries after its work item name, such as `_step_03.02_` read as (3, 2)."""
        actual_step_paths: list[tuple[int, ...]] = []
        for actual_filename in actual_filenames:
            step_path_match: re.Match[str] | None = _STEP_PATH_PATTERN.search(actual_filename)
            if step_path_match is not None:
                actual_step_paths.append(tuple(int(step_number) for step_number in step_path_match.group(1).split(".")))
        return actual_step_paths
