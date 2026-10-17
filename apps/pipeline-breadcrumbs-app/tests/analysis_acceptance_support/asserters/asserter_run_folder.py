import re
from collections.abc import Iterable, Mapping, Sequence, Set as AbstractSet
from dataclasses import dataclass, field
from pathlib import Path
from typing import Final

from breadcrumbs_acceptance_support.assertion_reports import format_assertion_report
from breadcrumbs_acceptance_support.manifest_documents import ManifestDocument, WorkItemRecordDocument

from pipeline_breadcrumbs_app.telemetry import ExceptionTelemetry

_TRACEBACK_HEADER: Final[str] = "Traceback (most recent call last)"
_RAW_DETECTION_RESPONSE_FRAGMENT: Final[str] = "raw_detection_response"
_RUN_ID_DIMENSION: Final[str] = "pipeline.run.id"
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
    """Compares what a demo run left behind, as the test gathered it, with what an engineer investigating the run should find.

    Every difference is reported at once.
    """

    RUN_OUTCOME_ASSERTION_FAILED_HEADER: Final[str] = "RUN OUTCOME ASSERTION FAILED"
    RUN_FOLDER_ASSERTION_FAILED_HEADER: Final[str] = "RUN FOLDER ASSERTION FAILED"
    WORK_ITEM_FILES_ASSERTION_FAILED_HEADER: Final[str] = "WORK ITEM FILES ASSERTION FAILED"
    STEP_ORDER_ASSERTION_FAILED_HEADER: Final[str] = "STEP ORDER ASSERTION FAILED"
    RAW_REPLIES_ASSERTION_FAILED_HEADER: Final[str] = "RAW REPLIES ASSERTION FAILED"
    DISTINCT_RUN_FOLDERS_ASSERTION_FAILED_HEADER: Final[str] = "DISTINCT RUN FOLDERS ASSERTION FAILED"
    WORK_ITEM_LISTINGS_ASSERTION_FAILED_HEADER: Final[str] = "WORK ITEM LISTINGS ASSERTION FAILED"
    FAILURE_LOG_ASSERTION_FAILED_HEADER: Final[str] = "FAILURE LOG ASSERTION FAILED"
    TELEMETRY_ASSERTION_FAILED_HEADER: Final[str] = "TELEMETRY ASSERTION FAILED"

    @staticmethod
    def assert_run_outcome(
        expected_run_outcome: ExpectedRunOutcome, actual_failed_work_item_names: Sequence[str], actual_manifest_document: ManifestDocument
    ) -> None:
        mismatches: list[str] = []
        if list(actual_failed_work_item_names) != list(expected_run_outcome.failed_work_item_names):
            mismatches.append(
                f"failed work items: expected {list(expected_run_outcome.failed_work_item_names)} but found {list(actual_failed_work_item_names)}"
            )
        if actual_manifest_document["pipeline_name"] != expected_run_outcome.pipeline_name:
            mismatches.append(
                f"pipeline name: expected {expected_run_outcome.pipeline_name!r} but found {actual_manifest_document['pipeline_name']!r}"
            )
        if actual_manifest_document["run_status"] != expected_run_outcome.run_status:
            mismatches.append(f"run status: expected {expected_run_outcome.run_status!r} but found {actual_manifest_document['run_status']!r}")
        for expected_work_item_outcome in expected_run_outcome.work_item_outcomes:
            mismatches.extend(AsserterRunFolder._compare_work_item(expected_work_item_outcome, actual_manifest_document["work_item_records"]))
        assert not mismatches, format_assertion_report(
            AsserterRunFolder.RUN_OUTCOME_ASSERTION_FAILED_HEADER,
            "The caller and the manifest agree on how the run and each document ended, step by step.",
            f"run '{expected_run_outcome.pipeline_name}' with {len(expected_run_outcome.work_item_outcomes)} work item(s) checked",
            mismatches,
        )

    @staticmethod
    def assert_exactly_these_entries(expected_entry_names: AbstractSet[str], actual_entry_names: Iterable[str]) -> None:
        actual_entry_name_set: set[str] = set(actual_entry_names)
        mismatches: list[str] = [
            *(f"missing entry {missing_name!r}" for missing_name in sorted(expected_entry_names - actual_entry_name_set)),
            *(f"unexpected entry {unexpected_name!r}" for unexpected_name in sorted(actual_entry_name_set - expected_entry_names)),
        ]
        assert not mismatches, format_assertion_report(
            AsserterRunFolder.RUN_FOLDER_ASSERTION_FAILED_HEADER,
            "The folder holds exactly the entries the run promises, and nothing else.",
            f"{len(expected_entry_names)} expected entr(ies), {len(actual_entry_name_set)} found",
            mismatches,
        )

    @staticmethod
    def assert_work_item_files(expected_file_start_by_filename: Mapping[str, str], actual_text_by_filename: Mapping[str, str]) -> None:
        """Each named file exists in the work item's folder and starts with the given text (empty text checks existence only)."""
        mismatches: list[str] = AsserterRunFolder._compare_file_starts(expected_file_start_by_filename, actual_text_by_filename)
        assert not mismatches, format_assertion_report(
            AsserterRunFolder.WORK_ITEM_FILES_ASSERTION_FAILED_HEADER,
            "The work item's folder holds each promised file, starting with its promised text.",
            f"{len(expected_file_start_by_filename)} file(s) expected among {len(actual_text_by_filename)} found",
            mismatches,
        )

    @staticmethod
    def assert_listing_in_step_order(
        expected_first_step_path: tuple[int, ...], actual_listing: Sequence[str], actual_folder_names: Sequence[str]
    ) -> None:
        mismatches: list[str] = []
        actual_step_paths: list[tuple[int, ...]] = AsserterRunFolder._read_step_paths(actual_listing)
        if len(actual_step_paths) != len(actual_listing):
            mismatches.append(f"every entry should carry a step path; {len(actual_listing) - len(actual_step_paths)} do not")
        if actual_step_paths != sorted(actual_step_paths):
            mismatches.append(f"step paths go backwards in an alphabetical listing: {actual_step_paths}")
        if not actual_step_paths or actual_step_paths[0] != expected_first_step_path:
            actual_first_step_path: tuple[int, ...] | str = actual_step_paths[0] if actual_step_paths else "no step path"
            mismatches.append(f"the listing should start at step {expected_first_step_path} but starts at {actual_first_step_path}")
        if actual_folder_names:
            mismatches.append(f"a work item folder holds only files, but found folders {list(actual_folder_names)}")
        assert not mismatches, format_assertion_report(
            AsserterRunFolder.STEP_ORDER_ASSERTION_FAILED_HEADER,
            "An ordinary alphabetical listing of a work item's folder reads in pipeline order.",
            f"{len(actual_listing)} entr(ies) listed",
            mismatches,
        )

    @staticmethod
    def assert_raw_replies(
        expected_raw_reply_filenames: Sequence[str], expected_reply_start_by_filename: Mapping[str, str], actual_text_by_filename: Mapping[str, str]
    ) -> None:
        mismatches: list[str] = []
        actual_raw_reply_filenames: list[str] = sorted(
            filename for filename in actual_text_by_filename if _RAW_DETECTION_RESPONSE_FRAGMENT in filename
        )
        if actual_raw_reply_filenames != list(expected_raw_reply_filenames):
            mismatches.append(f"raw replies: expected {list(expected_raw_reply_filenames)} but found {actual_raw_reply_filenames}")
        mismatches.extend(AsserterRunFolder._compare_file_starts(expected_reply_start_by_filename, actual_text_by_filename))
        assert not mismatches, format_assertion_report(
            AsserterRunFolder.RAW_REPLIES_ASSERTION_FAILED_HEADER,
            "Every raw model reply is kept as evidence, the one that failed to parse included.",
            f"{len(expected_raw_reply_filenames)} raw repl(ies) expected, {len(actual_raw_reply_filenames)} found",
            mismatches,
        )

    @staticmethod
    def assert_distinct_run_folders(
        expected_manifest_filename: str,
        actual_first_run_directory: Path,
        actual_second_run_directory: Path,
        actual_entry_names_by_run_directory: Mapping[Path, Sequence[str]],
    ) -> None:
        mismatches: list[str] = []
        if actual_first_run_directory == actual_second_run_directory:
            mismatches.append(f"both runs wrote to {actual_first_run_directory}")
        actual_run_directory: Path
        actual_entry_names: Sequence[str]
        for actual_run_directory, actual_entry_names in actual_entry_names_by_run_directory.items():
            if expected_manifest_filename not in actual_entry_names:
                mismatches.append(f"{actual_run_directory} has no {expected_manifest_filename}")
        assert not mismatches, format_assertion_report(
            AsserterRunFolder.DISTINCT_RUN_FOLDERS_ASSERTION_FAILED_HEADER,
            "Each run keeps its own folder, with its own manifest, so a second run never overwrites the first.",
            f"{len(actual_entry_names_by_run_directory)} run folder(s) checked",
            mismatches,
        )

    @staticmethod
    def assert_same_work_item_listings(
        expected_work_item_folder_names: Sequence[str],
        actual_local_listing_by_folder_name: Mapping[str, Sequence[str]],
        actual_hosted_listing_by_folder_name: Mapping[str, Sequence[str]],
    ) -> None:
        mismatches: list[str] = []
        for expected_folder_name in expected_work_item_folder_names:
            actual_local_listing: list[str] = list(actual_local_listing_by_folder_name.get(expected_folder_name, ()))
            actual_hosted_listing: list[str] = list(actual_hosted_listing_by_folder_name.get(expected_folder_name, ()))
            if actual_hosted_listing != actual_local_listing:
                mismatches.append(f"{expected_folder_name}: local {actual_local_listing} but hosted {actual_hosted_listing}")
        assert not mismatches, format_assertion_report(
            AsserterRunFolder.WORK_ITEM_LISTINGS_ASSERTION_FAILED_HEADER,
            "Where the application runs never changes the artifacts each work item leaves behind.",
            f"{len(expected_work_item_folder_names)} work item folder(s) compared",
            mismatches,
        )

    @staticmethod
    def assert_failure_logged_once(expected_host_log_line: str, expected_facts: Sequence[str], actual_run_log: str) -> None:
        """The application logs the exception once, its traceback after its own line, with every named fact; steps print no traceback."""
        mismatches: list[str] = []
        actual_host_line_count: int = actual_run_log.count(expected_host_log_line)
        if actual_host_line_count != 1:
            mismatches.append(f"expected {expected_host_log_line!r} once but found it {actual_host_line_count} time(s)")
        elif _TRACEBACK_HEADER not in actual_run_log or actual_run_log.index(_TRACEBACK_HEADER) < actual_run_log.index(expected_host_log_line):
            mismatches.append("the first traceback should follow the application's own line, not a step breadcrumb")
        mismatches.extend(f"missing fact {expected_fact!r}" for expected_fact in expected_facts if expected_fact not in actual_run_log)
        assert not mismatches, format_assertion_report(
            AsserterRunFolder.FAILURE_LOG_ASSERTION_FAILED_HEADER,
            "A failed document is logged once, by the application, with every fact needed to find where it failed.",
            f"run log of {len(actual_run_log.splitlines())} line(s), {len(expected_facts)} fact(s) expected",
            mismatches,
        )

    @staticmethod
    def assert_single_exception_telemetry(
        expected_exception_telemetry: ExpectedExceptionTelemetry,
        actual_exception_telemetry_records: Sequence[ExceptionTelemetry],
        actual_manifest_run_id: str,
    ) -> None:
        claim: str = "Only the exception reaches telemetry, carrying its facts and the identity of the run it belongs to."
        # A prerequisite: the other comparisons describe that one exception, so without exactly one there is nothing to compare.
        assert len(actual_exception_telemetry_records) == 1, format_assertion_report(
            AsserterRunFolder.TELEMETRY_ASSERTION_FAILED_HEADER,
            claim,
            f"run {actual_manifest_run_id}",
            [f"expected one exception but telemetry received {len(actual_exception_telemetry_records)}"],
        )
        actual_exception_telemetry: ExceptionTelemetry = actual_exception_telemetry_records[0]
        mismatches: list[str] = []
        if actual_exception_telemetry.severity != expected_exception_telemetry.severity:
            mismatches.append(f"severity: expected {expected_exception_telemetry.severity!r} but found {actual_exception_telemetry.severity!r}")
        if actual_exception_telemetry.exception_type != expected_exception_telemetry.exception_type:
            mismatches.append(
                f"exception type: expected {expected_exception_telemetry.exception_type!r} but found {actual_exception_telemetry.exception_type!r}"
            )
        if expected_exception_telemetry.stack_trace_phrase not in (actual_exception_telemetry.stack_trace or ""):
            mismatches.append(f"stack trace: expected the phrase {expected_exception_telemetry.stack_trace_phrase!r}")
        expected_name: str
        expected_value: object
        for expected_name, expected_value in expected_exception_telemetry.custom_dimensions.items():
            actual_value: object = actual_exception_telemetry.custom_dimensions.get(expected_name)
            if actual_value != expected_value:
                mismatches.append(f"custom dimension {expected_name!r}: expected {expected_value!r} but found {actual_value!r}")
        actual_run_id_dimension: object = actual_exception_telemetry.custom_dimensions.get(_RUN_ID_DIMENSION)
        if actual_run_id_dimension != actual_manifest_run_id:
            mismatches.append(f"run identity: telemetry carries {actual_run_id_dimension!r} but the manifest records run {actual_manifest_run_id!r}")
        expected_dimension_count: int = len(expected_exception_telemetry.custom_dimensions)
        assert not mismatches, format_assertion_report(
            AsserterRunFolder.TELEMETRY_ASSERTION_FAILED_HEADER,
            claim,
            f"{actual_exception_telemetry.exception_type} in run {actual_manifest_run_id}, {expected_dimension_count} dimension(s) expected",
            mismatches,
        )

    @staticmethod
    def _compare_work_item(
        expected_work_item_outcome: ExpectedWorkItemOutcome, actual_work_item_record_documents: Sequence[WorkItemRecordDocument]
    ) -> list[str]:
        matching_work_item_record_documents: list[WorkItemRecordDocument] = [
            actual_work_item_record_document
            for actual_work_item_record_document in actual_work_item_record_documents
            if actual_work_item_record_document["work_item_name"] == expected_work_item_outcome.name
        ]
        work_item_label: str = f"'{expected_work_item_outcome.name}'"
        if len(matching_work_item_record_documents) != 1:
            return [f"{work_item_label}: expected one record but found {len(matching_work_item_record_documents)}"]
        actual_work_item_record_document: WorkItemRecordDocument = matching_work_item_record_documents[0]
        mismatches: list[str] = []
        if actual_work_item_record_document["work_item_status"] != expected_work_item_outcome.work_item_status:
            mismatches.append(
                f"{work_item_label} status: expected {expected_work_item_outcome.work_item_status!r} "
                f"but found {actual_work_item_record_document['work_item_status']!r}"
            )
        actual_step_status_by_path: dict[str, str] = {
            actual_step_record_document["step_path"]: actual_step_record_document["step_status"]
            for actual_step_record_document in actual_work_item_record_document["step_records"]
        }
        if actual_step_status_by_path != dict(expected_work_item_outcome.step_status_by_path):
            mismatches.append(
                f"{work_item_label} steps: expected {dict(expected_work_item_outcome.step_status_by_path)} but found {actual_step_status_by_path}"
            )
        if expected_work_item_outcome.failure_phrase is not None and expected_work_item_outcome.failure_phrase not in (
            actual_work_item_record_document["failure"] or ""
        ):
            mismatches.append(f"{work_item_label} failure: expected the phrase {expected_work_item_outcome.failure_phrase!r}")
        actual_artifact_filenames: list[str] = [
            actual_artifact_record_document["filename"] for actual_artifact_record_document in actual_work_item_record_document["artifact_records"]
        ]
        mismatches.extend(
            f"{work_item_label}: expected an artifact named with {expected_fragment!r}"
            for expected_fragment in expected_work_item_outcome.present_artifact_fragments
            if not any(expected_fragment in actual_filename for actual_filename in actual_artifact_filenames)
        )
        mismatches.extend(
            f"{work_item_label}: expected no artifact named with {expected_fragment!r}"
            for expected_fragment in expected_work_item_outcome.absent_artifact_fragments
            if any(expected_fragment in actual_filename for actual_filename in actual_artifact_filenames)
        )
        return mismatches

    @staticmethod
    def _compare_file_starts(expected_start_by_filename: Mapping[str, str], actual_text_by_filename: Mapping[str, str]) -> list[str]:
        mismatches: list[str] = []
        expected_filename: str
        expected_start: str
        for expected_filename, expected_start in expected_start_by_filename.items():
            actual_text: str | None = actual_text_by_filename.get(expected_filename)
            if actual_text is None:
                mismatches.append(f"{expected_filename}: missing")
            elif not actual_text.startswith(expected_start):
                mismatches.append(f"{expected_filename}: expected it to start with {expected_start!r} but it starts with {actual_text[:40]!r}")
        return mismatches

    @staticmethod
    def _read_step_paths(actual_filenames: Iterable[str]) -> list[tuple[int, ...]]:
        """The step path each filename carries after its work item name, such as `_step_03.02_` read as (3, 2)."""
        actual_step_paths: list[tuple[int, ...]] = []
        for actual_filename in actual_filenames:
            step_path_match: re.Match[str] | None = _STEP_PATH_PATTERN.search(actual_filename)
            if step_path_match is not None:
                actual_step_paths.append(tuple(int(step_number) for step_number in step_path_match.group(1).split(".")))
        return actual_step_paths
