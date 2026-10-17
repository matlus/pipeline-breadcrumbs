from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Final

from breadcrumbs_acceptance_support.assertion_reports import format_assertion_report
from pipeline_breadcrumbs import ContextualExceptionProtocol

# The message is verified by its meaningful phrases, so its exact copy in the contextual data is not compared again.
_MESSAGE_ENTRY_NAME: Final[str] = "Message"
# An expected value that only requires the entry to be present, for a fact whose exact value a test cannot fix (a byte count of generated content).
ANY_CONTEXTUAL_VALUE: Final[object] = object()


@dataclass(frozen=True)
class ExpectedException:
    exception_type: type[BaseException]
    message_phrases: Sequence[str]
    contextual_data_by_name: Mapping[str, object] | None = None
    cause_type: type[BaseException] | None = None
    note_phrases: Sequence[str] = ()


class AsserterException:
    """Checks a raised exception's precise type, the phrases its message must contain, its named diagnostic data, its cause and its notes.

    Every difference is collected before one failure, so a test learns all of what is wrong at once.
    """

    EXCEPTION_ASSERTION_FAILED_HEADER: Final[str] = "EXCEPTION ASSERTION FAILED"

    @staticmethod
    def assert_exception(expected_exception: ExpectedException, actual_exception: BaseException) -> None:
        mismatches: list[str] = [
            *AsserterException._compare_type(expected_exception, actual_exception),
            *AsserterException._compare_message_phrases(expected_exception, actual_exception),
            *AsserterException._compare_contextual_data(expected_exception, actual_exception),
            *AsserterException._compare_cause(expected_exception, actual_exception),
            *AsserterException._compare_notes(expected_exception, actual_exception),
        ]
        assert not mismatches, format_assertion_report(
            AsserterException.EXCEPTION_ASSERTION_FAILED_HEADER,
            f"The failure surfaces as a {expected_exception.exception_type.__name__} that explains itself and carries its diagnostic facts.",
            f"raised {type(actual_exception).__name__}: {actual_exception}",
            mismatches,
        )

    @staticmethod
    def _compare_type(expected_exception: ExpectedException, actual_exception: BaseException) -> list[str]:
        if type(actual_exception) is expected_exception.exception_type:
            return []
        return [f"type: expected {expected_exception.exception_type.__name__} but found {type(actual_exception).__name__}"]

    @staticmethod
    def _compare_message_phrases(expected_exception: ExpectedException, actual_exception: BaseException) -> list[str]:
        actual_message: str = str(actual_exception)
        return [
            f"message: expected the phrase {expected_phrase!r}"
            for expected_phrase in expected_exception.message_phrases
            if expected_phrase not in actual_message
        ]

    @staticmethod
    def _compare_contextual_data(expected_exception: ExpectedException, actual_exception: BaseException) -> list[str]:
        if expected_exception.contextual_data_by_name is None:
            return []
        if not isinstance(actual_exception, ContextualExceptionProtocol):
            return ["contextual data: expected some, but the exception carries none"]
        actual_value_by_name: dict[str, object] = {
            actual_name: actual_value
            for actual_name, actual_value in actual_exception.contextual_data_by_name.items()
            if actual_name != _MESSAGE_ENTRY_NAME
        }
        contextual_mismatches: list[str] = []
        expected_name: str
        expected_value: object
        for expected_name, expected_value in expected_exception.contextual_data_by_name.items():
            if expected_name not in actual_value_by_name:
                contextual_mismatches.append(f"contextual data '{expected_name}': missing; expected {expected_value!r}")
            elif expected_value is not ANY_CONTEXTUAL_VALUE and actual_value_by_name[expected_name] != expected_value:
                contextual_mismatches.append(
                    f"contextual data '{expected_name}': expected {expected_value!r} but found {actual_value_by_name[expected_name]!r}"
                )
        contextual_mismatches.extend(
            f"contextual data '{actual_name}': not expected"
            for actual_name in actual_value_by_name
            if actual_name not in expected_exception.contextual_data_by_name
        )
        return contextual_mismatches

    @staticmethod
    def _compare_cause(expected_exception: ExpectedException, actual_exception: BaseException) -> list[str]:
        if expected_exception.cause_type is None or type(actual_exception.__cause__) is expected_exception.cause_type:
            return []
        return [f"cause: expected {expected_exception.cause_type.__name__} but found {type(actual_exception.__cause__).__name__}"]

    @staticmethod
    def _compare_notes(expected_exception: ExpectedException, actual_exception: BaseException) -> list[str]:
        actual_notes: str = "\n".join(getattr(actual_exception, "__notes__", []))
        return [
            f"notes: expected the phrase {expected_phrase!r} in {actual_notes!r}"
            for expected_phrase in expected_exception.note_phrases
            if expected_phrase not in actual_notes
        ]
