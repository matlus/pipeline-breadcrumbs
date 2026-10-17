from collections.abc import Sequence
from dataclasses import fields
from typing import Final

from breadcrumbs_acceptance_support.assertion_reports import format_assertion_report

from pipeline_breadcrumbs_app.document_analysis.models import ScoredSection


class AnalyzedSectionsAsserter:
    """Checks the sections an analysis returned, field by field and in page order, reporting every difference at once."""

    ANALYZED_SECTIONS_ASSERTION_FAILED_HEADER: Final[str] = "ANALYZED SECTIONS ASSERTION FAILED"

    @staticmethod
    def assert_expected_and_actual_are_equal(
        expected_scored_sections: Sequence[ScoredSection], actual_scored_sections: Sequence[ScoredSection]
    ) -> None:
        mismatches: list[str] = []
        position: int
        expected_scored_section: ScoredSection
        actual_scored_section: ScoredSection
        for position, (expected_scored_section, actual_scored_section) in enumerate(
            zip(expected_scored_sections, actual_scored_sections, strict=False)
        ):
            mismatches.extend(
                f"section {position} {section_field.name}: expected {getattr(expected_scored_section, section_field.name)!r} "
                f"but found {getattr(actual_scored_section, section_field.name)!r}"
                for section_field in fields(ScoredSection)
                if getattr(expected_scored_section, section_field.name) != getattr(actual_scored_section, section_field.name)
            )
        missing_scored_section: ScoredSection
        for position, missing_scored_section in enumerate(expected_scored_sections[len(actual_scored_sections) :], len(actual_scored_sections)):
            mismatches.append(f"section {position}: missing {missing_scored_section}")
        unexpected_scored_section: ScoredSection
        for position, unexpected_scored_section in enumerate(actual_scored_sections[len(expected_scored_sections) :], len(expected_scored_sections)):
            mismatches.append(f"section {position}: unexpected {unexpected_scored_section}")
        assert not mismatches, format_assertion_report(
            AnalyzedSectionsAsserter.ANALYZED_SECTIONS_ASSERTION_FAILED_HEADER,
            "Each section carries the title, category and confidence the model gave its page, in page order.",
            f"{len(expected_scored_sections)} section(s) expected, {len(actual_scored_sections)} returned",
            mismatches,
        )
