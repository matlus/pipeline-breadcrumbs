from collections.abc import Sequence
from typing import Final

from breadcrumbs_acceptance_support.assertion_reports import format_assertion_report
from pipeline_breadcrumbs import Artifact

_ARTIFACTS_ASSERTION_FAILED_HEADER: Final[str] = "ARTIFACT ASSERTION FAILED"


class ArtifactFilenamesAsserter:
    """Checks that a run handed its sink exactly the expected artifacts, in pipeline order."""

    @staticmethod
    def assert_expected_and_actual_are_equal(expected_filenames: Sequence[str], actual_artifacts: Sequence[Artifact]) -> None:
        actual_filenames: list[str] = [actual_artifact.filename for actual_artifact in actual_artifacts]
        mismatches: list[str] = []
        position: int
        expected_filename: str
        actual_filename: str
        for position, (expected_filename, actual_filename) in enumerate(zip(expected_filenames, actual_filenames, strict=False)):
            if expected_filename != actual_filename:
                mismatches.append(f"artifact {position}: expected {expected_filename!r} but found {actual_filename!r}")
        mismatches.extend(f"missing artifact {missing_filename!r}" for missing_filename in expected_filenames[len(actual_filenames) :])
        mismatches.extend(f"unexpected artifact {unexpected_filename!r}" for unexpected_filename in actual_filenames[len(expected_filenames) :])
        assert not mismatches, format_assertion_report(
            _ARTIFACTS_ASSERTION_FAILED_HEADER,
            "The run hands its sink exactly these artifacts, in pipeline order.",
            f"{len(expected_filenames)} expected artifact(s), {len(actual_filenames)} received",
            mismatches,
        )


class EmittedArtifactAsserter:
    """Checks that an emitted artifact carries its promised name and reaches the sink with its bytes unchanged."""

    @staticmethod
    def assert_expected_and_actual_are_equal(
        expected_filename: str, expected_content: bytes, actual_emitted_artifact: Artifact, actual_received_artifacts: Sequence[Artifact]
    ) -> None:
        mismatches: list[str] = []
        if actual_emitted_artifact.filename != expected_filename:
            mismatches.append(f"emitted filename: expected {expected_filename!r} but found {actual_emitted_artifact.filename!r}")
        actual_received_artifact: Artifact | None = next(
            (received_artifact for received_artifact in actual_received_artifacts if received_artifact.filename == expected_filename), None
        )
        if actual_received_artifact is None:
            mismatches.append(f"sink: expected to receive {expected_filename!r} but did not")
        elif actual_received_artifact.content != expected_content:
            mismatches.append(f"sink content: expected {expected_content!r} but found {actual_received_artifact.content!r}")
        assert not mismatches, format_assertion_report(
            _ARTIFACTS_ASSERTION_FAILED_HEADER,
            "An emitted artifact names itself as promised and reaches the sink with its bytes unchanged.",
            f"emitted {actual_emitted_artifact.filename!r}; the sink received {len(actual_received_artifacts)} artifact(s)",
            mismatches,
        )
