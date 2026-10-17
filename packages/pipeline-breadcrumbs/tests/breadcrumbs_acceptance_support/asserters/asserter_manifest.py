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
    manifest_steps: Sequence[ExpectedManifestStep] = ()
    artifact_filenames: Sequence[str] = field(default_factory=tuple[str, ...])
    artifact_role_by_filename: Mapping[str, str] | None = None


@dataclass(frozen=True)
class ExpectedManifest:
    pipeline_name: str
    run_id: str
    run_status: str
    elapsed_seconds: float
    manifest_work_items: Sequence[ExpectedManifestWorkItem]


class AsserterManifest:
    """Reads the run manifest the way an engineer would, and reports every difference from what the run should have recorded."""

    MANIFEST_ASSERTION_FAILED_HEADER: Final[str] = "MANIFEST ASSERTION FAILED"

    @staticmethod
    def assert_manifest(expected_manifest: ExpectedManifest, actual_manifest_artifact: Artifact) -> None:
        actual_manifest_document: ManifestDocument = parse_manifest_document(actual_manifest_artifact.content)
        mismatches: list[str] = []
        AsserterManifest._compare("artifact kind", MANIFEST_KIND, actual_manifest_artifact.artifact_kind, mismatches)
        AsserterManifest._compare("pipeline_name", expected_manifest.pipeline_name, actual_manifest_document["pipeline_name"], mismatches)
        AsserterManifest._compare("run_id", expected_manifest.run_id, actual_manifest_document["run_id"], mismatches)
        AsserterManifest._compare("run_status", expected_manifest.run_status, actual_manifest_document["run_status"], mismatches)
        AsserterManifest._compare("elapsed_seconds", expected_manifest.elapsed_seconds, actual_manifest_document["elapsed_seconds"], mismatches)
        actual_work_item_record_documents: list[WorkItemRecordDocument] = actual_manifest_document["work_item_records"]
        AsserterManifest._compare(
            "work item names",
            [expected_manifest_work_item.name for expected_manifest_work_item in expected_manifest.manifest_work_items],
            [actual_work_item_record_document["work_item_name"] for actual_work_item_record_document in actual_work_item_record_documents],
            mismatches,
        )
        expected_manifest_work_item: ExpectedManifestWorkItem
        actual_work_item_record_document: WorkItemRecordDocument
        for expected_manifest_work_item, actual_work_item_record_document in zip(
            expected_manifest.manifest_work_items, actual_work_item_record_documents, strict=False
        ):
            label: str = f"work item '{expected_manifest_work_item.name}'"
            AsserterManifest._compare(
                f"{label} status", expected_manifest_work_item.work_item_status, actual_work_item_record_document["work_item_status"], mismatches
            )
            AsserterManifest._compare(
                f"{label} failure", expected_manifest_work_item.failure, actual_work_item_record_document["failure"], mismatches
            )
            AsserterManifest._compare_artifacts(label, expected_manifest_work_item, actual_work_item_record_document["artifact_records"], mismatches)
            AsserterManifest._compare_steps(
                label, expected_manifest_work_item.manifest_steps, actual_work_item_record_document["step_records"], mismatches
            )
        expected_manifest_work_item_count: int = len(expected_manifest.manifest_work_items)
        actual_work_item_record_document_count: int = len(actual_work_item_record_documents)
        assert not mismatches, format_assertion_report(
            AsserterManifest.MANIFEST_ASSERTION_FAILED_HEADER,
            "The manifest records how the run, each work item and each step ended, and which artifacts each one left behind.",
            f"run '{expected_manifest.pipeline_name}': {expected_manifest_work_item_count} work item(s) expected, "
            f"{actual_work_item_record_document_count} found",
            mismatches,
        )

    @staticmethod
    def _compare_artifacts(
        label: str,
        expected_manifest_work_item: ExpectedManifestWorkItem,
        actual_artifact_record_documents: Sequence[ArtifactRecordDocument],
        mismatches: list[str],
    ) -> None:
        AsserterManifest._compare(
            f"{label} artifact filenames",
            list(expected_manifest_work_item.artifact_filenames),
            [actual_artifact_record_document["filename"] for actual_artifact_record_document in actual_artifact_record_documents],
            mismatches,
        )
        if expected_manifest_work_item.artifact_role_by_filename is not None:
            AsserterManifest._compare(
                f"{label} artifact roles",
                dict(expected_manifest_work_item.artifact_role_by_filename),
                {
                    actual_artifact_record_document["filename"]: actual_artifact_record_document["role"]
                    for actual_artifact_record_document in actual_artifact_record_documents
                },
                mismatches,
            )

    @staticmethod
    def _compare_steps(
        label: str,
        expected_manifest_steps: Sequence[ExpectedManifestStep],
        actual_step_record_documents: Sequence[StepRecordDocument],
        mismatches: list[str],
    ) -> None:
        AsserterManifest._compare(
            f"{label} step paths",
            [expected_manifest_step.path for expected_manifest_step in expected_manifest_steps],
            [actual_step_record_document["step_path"] for actual_step_record_document in actual_step_record_documents],
            mismatches,
        )
        expected_manifest_step: ExpectedManifestStep
        actual_step_record_document: StepRecordDocument
        for expected_manifest_step, actual_step_record_document in zip(expected_manifest_steps, actual_step_record_documents, strict=False):
            step_label: str = f"{label} step {expected_manifest_step.path}"
            AsserterManifest._compare(
                f"{step_label} status", expected_manifest_step.step_status, actual_step_record_document["step_status"], mismatches
            )
            AsserterManifest._compare(f"{step_label} outcome", expected_manifest_step.outcome, actual_step_record_document["outcome"], mismatches)
            AsserterManifest._compare(f"{step_label} failure", expected_manifest_step.failure, actual_step_record_document["failure"], mismatches)
            if expected_manifest_step.elapsed_seconds is not None:
                AsserterManifest._compare(
                    f"{step_label} elapsed", expected_manifest_step.elapsed_seconds, actual_step_record_document["elapsed_seconds"], mismatches
                )

    @staticmethod
    def _compare(subject: str, expected_value: object, actual_value: object, mismatches: list[str]) -> None:
        if expected_value != actual_value:
            mismatches.append(f"{subject}: expected {expected_value!r} but found {actual_value!r}")
