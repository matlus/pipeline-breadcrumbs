import json
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

from pipeline_breadcrumbs import Artifact


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
    artifact_filenames: Sequence[str] = field(default_factory=tuple)


@dataclass(frozen=True)
class ExpectedManifest:
    pipeline_name: str
    run_id: str
    run_status: str
    elapsed_seconds: float
    work_item_records: Sequence[ExpectedManifestWorkItem]


class AsserterManifest:
    """Reads the run manifest the way an engineer would, and reports every difference from what the run should have recorded."""

    @staticmethod
    def assert_manifest(expected_manifest: ExpectedManifest, actual_manifest_artifact: Artifact) -> None:
        actual_manifest: dict[str, Any] = json.loads(actual_manifest_artifact.content)
        assertion_failures: list[str] = []
        AsserterManifest._compare("pipeline_name", expected_manifest.pipeline_name, actual_manifest["pipeline_name"], assertion_failures)
        AsserterManifest._compare("run_id", expected_manifest.run_id, actual_manifest["run_id"], assertion_failures)
        AsserterManifest._compare("run_status", expected_manifest.run_status, actual_manifest["run_status"], assertion_failures)
        AsserterManifest._compare("elapsed_seconds", expected_manifest.elapsed_seconds, actual_manifest["elapsed_seconds"], assertion_failures)
        actual_work_item_records: list[dict[str, Any]] = actual_manifest["work_item_records"]
        AsserterManifest._compare(
            "work item names",
            [expected_work_item.name for expected_work_item in expected_manifest.work_item_records],
            [actual_work_item["work_item_name"] for actual_work_item in actual_work_item_records],
            assertion_failures,
        )
        for expected_work_item, actual_work_item in zip(expected_manifest.work_item_records, actual_work_item_records, strict=False):
            AsserterManifest._compare_work_item(expected_work_item, actual_work_item, assertion_failures)
        assert not assertion_failures, "MANIFEST ASSERTION FAILED\n" + "\n".join(assertion_failures)

    @staticmethod
    def _compare_work_item(expected_work_item: ExpectedManifestWorkItem, actual_work_item: dict[str, Any], assertion_failures: list[str]) -> None:
        label: str = f"work item '{expected_work_item.name}'"
        AsserterManifest._compare(f"{label} status", expected_work_item.work_item_status, actual_work_item["work_item_status"], assertion_failures)
        AsserterManifest._compare(f"{label} failure", expected_work_item.failure, actual_work_item["failure"], assertion_failures)
        AsserterManifest._compare(
            f"{label} artifact filenames",
            list(expected_work_item.artifact_filenames),
            [actual_artifact["filename"] for actual_artifact in actual_work_item["artifact_records"]],
            assertion_failures,
        )
        actual_step_records: list[dict[str, Any]] = actual_work_item["step_records"]
        AsserterManifest._compare(
            f"{label} step paths",
            [expected_step.path for expected_step in expected_work_item.step_records],
            [actual_step["step_path"] for actual_step in actual_step_records],
            assertion_failures,
        )
        for expected_step, actual_step in zip(expected_work_item.step_records, actual_step_records, strict=False):
            step_label: str = f"{label} step {expected_step.path}"
            AsserterManifest._compare(f"{step_label} status", expected_step.step_status, actual_step["step_status"], assertion_failures)
            AsserterManifest._compare(f"{step_label} outcome", expected_step.outcome, actual_step["outcome"], assertion_failures)
            AsserterManifest._compare(f"{step_label} failure", expected_step.failure, actual_step["failure"], assertion_failures)
            if expected_step.elapsed_seconds is not None:
                AsserterManifest._compare(f"{step_label} elapsed", expected_step.elapsed_seconds, actual_step["elapsed_seconds"], assertion_failures)

    @staticmethod
    def _compare(subject: str, expected_value: object, actual_value: object, assertion_failures: list[str]) -> None:
        if expected_value != actual_value:
            assertion_failures.append(f"{subject}: expected {expected_value!r} but found {actual_value!r}")
