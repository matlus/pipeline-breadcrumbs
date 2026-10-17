from collections.abc import Sequence

from pipeline_breadcrumbs import Artifact, ArtifactKind, ArtifactRole, StepArtifact


class AsserterAnalysisArtifacts:
    """Checks the trail an analysis handed to its sink: every file in pipeline order, which of them are outputs, and the report."""

    @staticmethod
    def assert_trail(
        expected_filenames: Sequence[str],
        expected_output_filenames: Sequence[str],
        expected_report_kind: ArtifactKind,
        expected_report_heading: str,
        actual_artifacts: Sequence[Artifact],
    ) -> None:
        assertion_failures: list[str] = []
        actual_filenames: list[str] = [actual_artifact.filename for actual_artifact in actual_artifacts]
        if actual_filenames != list(expected_filenames):
            assertion_failures.append(f"filenames:\n  expected {list(expected_filenames)}\n  actual   {actual_filenames}")
        actual_output_filenames: list[str] = [
            actual_artifact.filename
            for actual_artifact in actual_artifacts
            if isinstance(actual_artifact, StepArtifact) and actual_artifact.artifact_kind.role is ArtifactRole.OUTPUT
        ]
        if actual_output_filenames != list(expected_output_filenames):
            assertion_failures.append(f"outputs: expected {list(expected_output_filenames)} but found {actual_output_filenames}")
        actual_reports: list[Artifact] = [
            actual_artifact for actual_artifact in actual_artifacts if actual_artifact.artifact_kind == expected_report_kind
        ]
        if len(actual_reports) != 1:
            assertion_failures.append(f"report: expected exactly one but found {len(actual_reports)}")
        elif not actual_reports[0].content.decode("utf-8").startswith(expected_report_heading):
            assertion_failures.append(f"report: expected it to start with {expected_report_heading!r}")
        assert not assertion_failures, "ANALYSIS ARTIFACTS ASSERTION FAILED\n" + "\n".join(assertion_failures)
