from collections.abc import Sequence

from pipeline_breadcrumbs import Artifact


class AsserterArtifacts:
    """Checks the artifacts a run handed to its sink."""

    @staticmethod
    def assert_exactly_these_filenames_in_order(expected_filenames: Sequence[str], actual_artifacts: Sequence[Artifact]) -> None:
        actual_filenames: list[str] = [actual_artifact.filename for actual_artifact in actual_artifacts]
        assert list(expected_filenames) == actual_filenames, (
            f"ARTIFACT ASSERTION FAILED\nexpected filenames: {list(expected_filenames)}\nactual filenames:   {actual_filenames}"
        )
