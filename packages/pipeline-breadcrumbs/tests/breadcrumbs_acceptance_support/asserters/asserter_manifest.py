from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Final

from breadcrumbs_acceptance_support.assertion_reports import format_assertion_report
from breadcrumbs_acceptance_support.manifest_documents import (
    ArtifactRecordDocument,
    ManifestDocument,
    RunArtifactRecordDocument,
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
class ExpectedManifestRunArtifact:
    filename: str
    artifact_type: str
    role: str
    byte_count: int


@dataclass(frozen=True)
class ExpectedManifest:
    pipeline_name: str
    run_id: str
    run_status: str
    elapsed_seconds: float
    manifest_work_items: Sequence[ExpectedManifestWorkItem]
    manifest_run_artifacts: Sequence[ExpectedManifestRunArtifact] = ()


class ManifestAsserter:
    """Reads the run manifest the way an engineer would, and reports every difference from what the run should have recorded."""

    MANIFEST_ASSERTION_FAILED_HEADER: Final[str] = "MANIFEST ASSERTION FAILED"

    @staticmethod
    def assert_expected_and_actual_are_equal(expected_manifest: ExpectedManifest, actual_manifest_artifact: Artifact) -> None:
        business_claim: str = "The manifest records how the run, each work item and each step ended, and which artifacts each one left behind."
        # A prerequisite: only a manifest can be read as one, so any other artifact is reported before its content is parsed.
        artifact_kind_mismatch: str = (
            f"artifact kind: expected {MANIFEST_KIND!r} but found {actual_manifest_artifact.artifact_kind!r} in {actual_manifest_artifact.filename!r}"
        )
        assert actual_manifest_artifact.artifact_kind == MANIFEST_KIND, format_assertion_report(
            ManifestAsserter.MANIFEST_ASSERTION_FAILED_HEADER, business_claim, f"run '{expected_manifest.pipeline_name}'", [artifact_kind_mismatch]
        )
        actual_manifest_document: ManifestDocument = parse_manifest_document(actual_manifest_artifact.content)
        mismatches: list[str] = []
        ManifestAsserter._compare("pipeline_name", expected_manifest.pipeline_name, actual_manifest_document["pipeline_name"], mismatches)
        ManifestAsserter._compare("run_id", expected_manifest.run_id, actual_manifest_document["run_id"], mismatches)
        ManifestAsserter._compare("run_status", expected_manifest.run_status, actual_manifest_document["run_status"], mismatches)
        ManifestAsserter._compare("elapsed_seconds", expected_manifest.elapsed_seconds, actual_manifest_document["elapsed_seconds"], mismatches)
        actual_work_item_record_documents: list[WorkItemRecordDocument] = actual_manifest_document["work_item_records"]
        ManifestAsserter._compare(
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
            ManifestAsserter._compare(
                f"{label} status", expected_manifest_work_item.work_item_status, actual_work_item_record_document["work_item_status"], mismatches
            )
            ManifestAsserter._compare(
                f"{label} failure", expected_manifest_work_item.failure, actual_work_item_record_document["failure"], mismatches
            )
            mismatches.extend(
                ManifestAsserter._compare_artifacts(
                    label,
                    expected_manifest_work_item.artifact_filenames,
                    expected_manifest_work_item.artifact_role_by_filename,
                    actual_work_item_record_document["artifact_records"],
                )
            )
            ManifestAsserter._compare_steps(
                label, expected_manifest_work_item.manifest_steps, actual_work_item_record_document["step_records"], mismatches
            )
        ManifestAsserter._compare_run_artifacts(
            expected_manifest.manifest_run_artifacts, actual_manifest_document["run_artifact_records"], mismatches
        )
        expected_manifest_work_item_count: int = len(expected_manifest.manifest_work_items)
        actual_work_item_record_document_count: int = len(actual_work_item_record_documents)
        assert not mismatches, format_assertion_report(
            ManifestAsserter.MANIFEST_ASSERTION_FAILED_HEADER,
            business_claim,
            f"run '{expected_manifest.pipeline_name}': {expected_manifest_work_item_count} work item(s) expected, "
            f"{actual_work_item_record_document_count} found",
            mismatches,
        )

    @staticmethod
    def _compare_run_artifacts(
        expected_manifest_run_artifacts: Sequence[ExpectedManifestRunArtifact],
        actual_run_artifact_record_documents: Sequence[RunArtifactRecordDocument],
        mismatches: list[str],
    ) -> None:
        # The filenames line names every missing and unexpected record; each matched record then reports its own differing fields.
        ManifestAsserter._compare(
            "run artifact filenames",
            [expected_manifest_run_artifact.filename for expected_manifest_run_artifact in expected_manifest_run_artifacts],
            [actual_run_artifact_record_document["filename"] for actual_run_artifact_record_document in actual_run_artifact_record_documents],
            mismatches,
        )
        actual_run_artifact_record_document_by_filename: dict[str, RunArtifactRecordDocument] = {
            actual_run_artifact_record_document["filename"]: actual_run_artifact_record_document
            for actual_run_artifact_record_document in actual_run_artifact_record_documents
        }
        for expected_manifest_run_artifact in expected_manifest_run_artifacts:
            actual_run_artifact_record_document: RunArtifactRecordDocument | None = actual_run_artifact_record_document_by_filename.get(
                expected_manifest_run_artifact.filename
            )
            if actual_run_artifact_record_document is None:
                continue
            label: str = f"run artifact '{expected_manifest_run_artifact.filename}'"
            ManifestAsserter._compare(
                f"{label} artifact type",
                expected_manifest_run_artifact.artifact_type,
                actual_run_artifact_record_document["artifact_type"],
                mismatches,
            )
            ManifestAsserter._compare(f"{label} role", expected_manifest_run_artifact.role, actual_run_artifact_record_document["role"], mismatches)
            ManifestAsserter._compare(
                f"{label} byte count", expected_manifest_run_artifact.byte_count, actual_run_artifact_record_document["byte_count"], mismatches
            )

    @staticmethod
    def _compare_artifacts(
        label: str,
        expected_artifact_filenames: Sequence[str],
        expected_artifact_role_by_filename: Mapping[str, str] | None,
        actual_artifact_record_documents: Sequence[ArtifactRecordDocument],
    ) -> list[str]:
        mismatches: list[str] = []
        ManifestAsserter._compare(
            f"{label} artifact filenames",
            list(expected_artifact_filenames),
            [actual_artifact_record_document["filename"] for actual_artifact_record_document in actual_artifact_record_documents],
            mismatches,
        )
        if expected_artifact_role_by_filename is not None:
            ManifestAsserter._compare(
                f"{label} artifact roles",
                dict(expected_artifact_role_by_filename),
                {
                    actual_artifact_record_document["filename"]: actual_artifact_record_document["role"]
                    for actual_artifact_record_document in actual_artifact_record_documents
                },
                mismatches,
            )
        return mismatches

    @staticmethod
    def _compare_steps(
        label: str,
        expected_manifest_steps: Sequence[ExpectedManifestStep],
        actual_step_record_documents: Sequence[StepRecordDocument],
        mismatches: list[str],
    ) -> None:
        ManifestAsserter._compare(
            f"{label} step paths",
            [expected_manifest_step.path for expected_manifest_step in expected_manifest_steps],
            [actual_step_record_document["step_path"] for actual_step_record_document in actual_step_record_documents],
            mismatches,
        )
        expected_manifest_step: ExpectedManifestStep
        actual_step_record_document: StepRecordDocument
        for expected_manifest_step, actual_step_record_document in zip(expected_manifest_steps, actual_step_record_documents, strict=False):
            step_label: str = f"{label} step {expected_manifest_step.path}"
            ManifestAsserter._compare(
                f"{step_label} status", expected_manifest_step.step_status, actual_step_record_document["step_status"], mismatches
            )
            ManifestAsserter._compare(f"{step_label} outcome", expected_manifest_step.outcome, actual_step_record_document["outcome"], mismatches)
            ManifestAsserter._compare(f"{step_label} failure", expected_manifest_step.failure, actual_step_record_document["failure"], mismatches)
            if expected_manifest_step.elapsed_seconds is not None:
                ManifestAsserter._compare(
                    f"{step_label} elapsed", expected_manifest_step.elapsed_seconds, actual_step_record_document["elapsed_seconds"], mismatches
                )

    @staticmethod
    def _compare(subject: str, expected_value: object, actual_value: object, mismatches: list[str]) -> None:
        if expected_value != actual_value:
            mismatches.append(f"{subject}: expected {expected_value!r} but found {actual_value!r}")
