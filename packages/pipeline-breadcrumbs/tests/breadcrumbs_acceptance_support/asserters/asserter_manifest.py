from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Final

from breadcrumbs_acceptance_support.assertion_reports import format_assertion_report
from breadcrumbs_acceptance_support.manifest_documents import (
    ArtifactRecordDocument,
    ManifestDocument,
    StepRecordDocument,
    WorkItemRecordDocument,
    parse_manifest_document,
)
from pipeline_breadcrumbs import MANIFEST_KIND, Artifact


@dataclass(frozen=True)
class ExpectedManifestStep:
    path: str
    step_status: str
    elapsed_seconds: float | None = None
    outcome: str | None = None
    failure: str | None = None


@dataclass(frozen=True)
class ExpectedManifestWorkItem:
    name: str
    work_item_status: str
    failure: str | None = None
    step_records: Sequence[ExpectedManifestStep] = ()
    artifact_filenames: Sequence[str] = field(default_factory=tuple[str, ...])
    artifact_role_by_filename: Mapping[str, str] | None = None


@dataclass(frozen=True)
class ExpectedManifest:
    pipeline_name: str
    run_id: str
    run_status: str
    elapsed_seconds: float
    work_item_records: Sequence[ExpectedManifestWorkItem]


class AsserterManifest:
    """Reads the run manifest the way an engineer would, and reports every difference from what the run should have recorded."""

    MANIFEST_ASSERTION_FAILED_HEADER: Final[str] = "MANIFEST ASSERTION FAILED"

    @staticmethod
    def assert_manifest(expected_manifest: ExpectedManifest, actual_manifest_artifact: Artifact) -> None:
        actual_manifest: ManifestDocument = parse_manifest_document(actual_manifest_artifact.content)
        mismatches: list[str] = []
        AsserterManifest._compare("artifact kind", MANIFEST_KIND, actual_manifest_artifact.artifact_kind, mismatches)
        AsserterManifest._compare("pipeline_name", expected_manifest.pipeline_name, actual_manifest["pipeline_name"], mismatches)
        AsserterManifest._compare("run_id", expected_manifest.run_id, actual_manifest["run_id"], mismatches)
        AsserterManifest._compare("run_status", expected_manifest.run_status, actual_manifest["run_status"], mismatches)
        AsserterManifest._compare("elapsed_seconds", expected_manifest.elapsed_seconds, actual_manifest["elapsed_seconds"], mismatches)
        actual_work_item_records: list[WorkItemRecordDocument] = actual_manifest["work_item_records"]
        AsserterManifest._compare(
            "work item names",
            [expected_manifest_work_item.name for expected_manifest_work_item in expected_manifest.work_item_records],
            [actual_work_item_record["work_item_name"] for actual_work_item_record in actual_work_item_records],
            mismatches,
        )
        expected_manifest_work_item: ExpectedManifestWorkItem
        actual_work_item_record: WorkItemRecordDocument
        for expected_manifest_work_item, actual_work_item_record in zip(expected_manifest.work_item_records, actual_work_item_records, strict=False):
            AsserterManifest._compare_work_item(expected_manifest_work_item, actual_work_item_record, mismatches)
        expected_count: int = len(expected_manifest.work_item_records)
        assert not mismatches, format_assertion_report(
            AsserterManifest.MANIFEST_ASSERTION_FAILED_HEADER,
            "The manifest records how the run, each work item and each step ended, and which artifacts each one left behind.",
            f"run '{expected_manifest.pipeline_name}': {expected_count} work item(s) expected, {len(actual_work_item_records)} found",
            mismatches,
        )

    @staticmethod
    def _compare_work_item(
        expected_manifest_work_item: ExpectedManifestWorkItem, actual_work_item_record: WorkItemRecordDocument, mismatches: list[str]
    ) -> None:
        label: str = f"work item '{expected_manifest_work_item.name}'"
        AsserterManifest._compare(
            f"{label} status", expected_manifest_work_item.work_item_status, actual_work_item_record["work_item_status"], mismatches
        )
        AsserterManifest._compare(f"{label} failure", expected_manifest_work_item.failure, actual_work_item_record["failure"], mismatches)
        actual_artifact_records: list[ArtifactRecordDocument] = actual_work_item_record["artifact_records"]
        AsserterManifest._compare(
            f"{label} artifact filenames",
            list(expected_manifest_work_item.artifact_filenames),
            [actual_artifact_record["filename"] for actual_artifact_record in actual_artifact_records],
            mismatches,
        )
        if expected_manifest_work_item.artifact_role_by_filename is not None:
            AsserterManifest._compare(
                f"{label} artifact roles",
                dict(expected_manifest_work_item.artifact_role_by_filename),
                {actual_artifact_record["filename"]: actual_artifact_record["role"] for actual_artifact_record in actual_artifact_records},
                mismatches,
            )
        actual_step_records: list[StepRecordDocument] = actual_work_item_record["step_records"]
        AsserterManifest._compare(
            f"{label} step paths",
            [expected_manifest_step.path for expected_manifest_step in expected_manifest_work_item.step_records],
            [actual_step_record["step_path"] for actual_step_record in actual_step_records],
            mismatches,
        )
        expected_manifest_step: ExpectedManifestStep
        actual_step_record: StepRecordDocument
        for expected_manifest_step, actual_step_record in zip(expected_manifest_work_item.step_records, actual_step_records, strict=False):
            step_label: str = f"{label} step {expected_manifest_step.path}"
            AsserterManifest._compare(f"{step_label} status", expected_manifest_step.step_status, actual_step_record["step_status"], mismatches)
            AsserterManifest._compare(f"{step_label} outcome", expected_manifest_step.outcome, actual_step_record["outcome"], mismatches)
            AsserterManifest._compare(f"{step_label} failure", expected_manifest_step.failure, actual_step_record["failure"], mismatches)
            if expected_manifest_step.elapsed_seconds is not None:
                AsserterManifest._compare(
                    f"{step_label} elapsed", expected_manifest_step.elapsed_seconds, actual_step_record["elapsed_seconds"], mismatches
                )

    @staticmethod
    def _compare(subject: str, expected_value: object, actual_value: object, mismatches: list[str]) -> None:
        if expected_value != actual_value:
            mismatches.append(f"{subject}: expected {expected_value!r} but found {actual_value!r}")
