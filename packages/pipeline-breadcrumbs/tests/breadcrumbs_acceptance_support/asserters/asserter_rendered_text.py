import re
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Final

from breadcrumbs_acceptance_support.assertion_reports import format_assertion_report


@dataclass(frozen=True)
class ExpectedRenderedText:
    starts_with: str | None = None
    ends_with: str | None = None
    contained_phrases: Sequence[str] = field(default_factory=tuple[str, ...])
    absent_phrases: Sequence[str] = field(default_factory=tuple[str, ...])
    present_patterns: Sequence[re.Pattern[str]] = field(default_factory=tuple[re.Pattern[str], ...])
    absent_patterns: Sequence[re.Pattern[str]] = field(default_factory=tuple[re.Pattern[str], ...])


class AsserterRenderedText:
    """Checks the text a formatter produced against everything it should and should not contain, reporting every difference at once."""

    RENDERED_TEXT_ASSERTION_FAILED_HEADER: Final[str] = "RENDERED TEXT ASSERTION FAILED"
    _BUSINESS_CLAIM: Final[str] = "A person reading the trail sees the text the rendering promises, and nothing it rules out."

    @staticmethod
    def assert_text(expected_rendered_text: ExpectedRenderedText, actual_text: str) -> None:
        mismatches: list[str] = AsserterRenderedText._compare(expected_rendered_text, actual_text)
        assert not mismatches, format_assertion_report(
            AsserterRenderedText.RENDERED_TEXT_ASSERTION_FAILED_HEADER, AsserterRenderedText._BUSINESS_CLAIM, f"text {actual_text!r}", mismatches
        )

    @staticmethod
    def assert_every_text(expected_rendered_text: ExpectedRenderedText, actual_texts: Sequence[str]) -> None:
        mismatches: list[str] = [] if actual_texts else ["expected rendered texts, but there were none"]
        for actual_text in actual_texts:
            mismatches.extend(
                f"{actual_text!r}: {text_mismatch}" for text_mismatch in AsserterRenderedText._compare(expected_rendered_text, actual_text)
            )
        assert not mismatches, format_assertion_report(
            AsserterRenderedText.RENDERED_TEXT_ASSERTION_FAILED_HEADER,
            AsserterRenderedText._BUSINESS_CLAIM,
            f"{len(actual_texts)} text(s) checked",
            mismatches,
        )

    @staticmethod
    def _compare(expected_rendered_text: ExpectedRenderedText, actual_text: str) -> list[str]:
        text_mismatches: list[str] = []
        if expected_rendered_text.starts_with is not None and not actual_text.startswith(expected_rendered_text.starts_with):
            text_mismatches.append(f"expected it to start with {expected_rendered_text.starts_with!r}")
        if expected_rendered_text.ends_with is not None and not actual_text.endswith(expected_rendered_text.ends_with):
            text_mismatches.append(f"expected it to end with {expected_rendered_text.ends_with!r}")
        text_mismatches.extend(f"expected the phrase {phrase!r}" for phrase in expected_rendered_text.contained_phrases if phrase not in actual_text)
        text_mismatches.extend(f"expected no {phrase!r}" for phrase in expected_rendered_text.absent_phrases if phrase in actual_text)
        text_mismatches.extend(
            f"expected a match for {pattern.pattern!r}" for pattern in expected_rendered_text.present_patterns if not pattern.search(actual_text)
        )
        text_mismatches.extend(
            f"expected no match for {pattern.pattern!r}" for pattern in expected_rendered_text.absent_patterns if pattern.search(actual_text)
        )
        return text_mismatches
