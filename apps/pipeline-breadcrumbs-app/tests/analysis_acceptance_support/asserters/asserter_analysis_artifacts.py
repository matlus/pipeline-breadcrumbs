from collections.abc import Sequence
from typing import Final

from breadcrumbs_acceptance_support.assertion_reports import format_assertion_report

from pipeline_breadcrumbs import Artifact, ArtifactKind, ArtifactRole, StepArtifact


class AsserterAnalysisArtifacts:
    """Checks the trail an analysis handed to its sink: every file in pipeline order, which of them are outputs, and the report."""

    ANALYSIS_ARTIFACTS_ASSERTION_FAILED_HEADER: Final[str] = "ANALYSIS ARTIFACTS ASSERTION FAILED"

    @staticmethod
    def assert_trail(
        expected_filenames: Sequence[str],
        expected_output_filenames: Sequence[str],
        expected_report_kind: ArtifactKind,
        expected_report_heading: str,
        actual_artifacts: Sequence[Artifact],
    ) -> None:
        mismatches: list[str] = []
        actual_filenames: list[str] = [actual_artifact.filename for actual_artifact in actual_artifacts]
        if actual_filenames != list(expected_filenames):
            mismatches.append(f"filenames: expected {list(expected_filenames)} but found {actual_filenames}")
        actual_output_filenames: list[str] = [
            actual_artifact.filename
            for actual_artifact in actual_artifacts
            if isinstance(actual_artifact, StepArtifact) and actual_artifact.artifact_kind.role is ArtifactRole.OUTPUT
        ]
        if actual_output_filenames != list(expected_output_filenames):
            mismatches.append(f"outputs: expected {list(expected_output_filenames)} but found {actual_output_filenames}")
        actual_reports: list[Artifact] = [
            actual_artifact for actual_artifact in actual_artifacts if actual_artifact.artifact_kind == expected_report_kind
        ]
        if len(actual_reports) != 1:
            mismatches.append(f"report: expected exactly one but found {len(actual_reports)}")
        else:
            actual_report_text: str = actual_reports[0].content.decode("utf-8")
            if not actual_report_text.startswith(expected_report_heading):
                mismatches.append(f"report: expected it to start with {expected_report_heading!r} but it starts with {actual_report_text[:40]!r}")
        assert not mismatches, format_assertion_report(
            AsserterAnalysisArtifacts.ANALYSIS_ARTIFACTS_ASSERTION_FAILED_HEADER,
            "The analysis leaves its whole trail in pipeline order, marks its outputs, and ends with one report.",
            f"{len(expected_filenames)} artifact(s) expected, {len(actual_artifacts)} received",
            mismatches,
        )
