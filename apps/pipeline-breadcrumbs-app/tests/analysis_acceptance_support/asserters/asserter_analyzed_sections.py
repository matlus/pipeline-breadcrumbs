from collections.abc import Sequence

from pipeline_breadcrumbs_app.document_analysis.models import ScoredSection


class AsserterAnalyzedSections:
    """Checks the sections the system returned, and reports every difference at once."""

    @staticmethod
    def assert_exactly_these_sections(expected_scored_sections: Sequence[ScoredSection], actual_scored_sections: Sequence[ScoredSection]) -> None:
        assertion_failures: list[str] = []
        if len(expected_scored_sections) != len(actual_scored_sections):
            assertion_failures.append(f"expected {len(expected_scored_sections)} sections but found {len(actual_scored_sections)}")
        for expected_scored_section, actual_scored_section in zip(expected_scored_sections, actual_scored_sections, strict=False):
            if expected_scored_section != actual_scored_section:
                assertion_failures.append(f"expected {expected_scored_section} but found {actual_scored_section}")
        assert not assertion_failures, "ANALYZED SECTIONS ASSERTION FAILED\n" + "\n".join(assertion_failures)
