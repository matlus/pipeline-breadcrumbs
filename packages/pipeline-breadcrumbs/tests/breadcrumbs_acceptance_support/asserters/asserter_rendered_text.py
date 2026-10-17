import re
from collections.abc import Sequence
from dataclasses import dataclass, field


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

    @staticmethod
    def assert_text(expected_rendered_text: ExpectedRenderedText, actual_text: str) -> None:
        assertion_failures: list[str] = AsserterRenderedText._compare(expected_rendered_text, actual_text)
        assert not assertion_failures, f"RENDERED TEXT ASSERTION FAILED for {actual_text!r}\n" + "\n".join(assertion_failures)

    @staticmethod
    def assert_every_text(expected_rendered_text: ExpectedRenderedText, actual_texts: Sequence[str]) -> None:
        assert actual_texts, "RENDERED TEXT ASSERTION FAILED\nexpected rendered texts but there were none"
        assertion_failures: list[str] = [
            f"{actual_text!r}: {text_failure}"
            for actual_text in actual_texts
            for text_failure in AsserterRenderedText._compare(expected_rendered_text, actual_text)
        ]
        assert not assertion_failures, "RENDERED TEXT ASSERTION FAILED\n" + "\n".join(assertion_failures)

    @staticmethod
    def _compare(expected_rendered_text: ExpectedRenderedText, actual_text: str) -> list[str]:
        text_failures: list[str] = []
        if expected_rendered_text.starts_with is not None and not actual_text.startswith(expected_rendered_text.starts_with):
            text_failures.append(f"expected it to start with {expected_rendered_text.starts_with!r}")
        if expected_rendered_text.ends_with is not None and not actual_text.endswith(expected_rendered_text.ends_with):
            text_failures.append(f"expected it to end with {expected_rendered_text.ends_with!r}")
        text_failures.extend(f"expected the phrase {phrase!r}" for phrase in expected_rendered_text.contained_phrases if phrase not in actual_text)
        text_failures.extend(f"expected no {phrase!r}" for phrase in expected_rendered_text.absent_phrases if phrase in actual_text)
        text_failures.extend(
            f"expected a match for {pattern.pattern!r}" for pattern in expected_rendered_text.present_patterns if not pattern.search(actual_text)
        )
        text_failures.extend(
            f"expected no match for {pattern.pattern!r}" for pattern in expected_rendered_text.absent_patterns if pattern.search(actual_text)
        )
        return text_failures
