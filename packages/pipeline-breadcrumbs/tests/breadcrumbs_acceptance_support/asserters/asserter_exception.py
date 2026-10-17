from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from pipeline_breadcrumbs import ContextualExceptionProtocol

# The message is verified by its meaningful phrases, so its exact copy in the contextual data is not compared again.
_MESSAGE_ENTRY_NAME: str = "Message"


@dataclass(frozen=True)
class ExpectedException:
    exception_type: type[BaseException]
    message_phrases: Sequence[str]
    contextual_data_by_name: Mapping[str, object] | None = None
    cause_type: type[BaseException] | None = None


class AsserterException:
    """Checks a raised exception's precise type, the phrases its message must contain, its named diagnostic data and its cause.

    Every difference is collected before one failure, so a test learns all of what is wrong at once.
    """

    @staticmethod
    def assert_exception(expected_exception: ExpectedException, actual_exception: BaseException) -> None:
        assertion_failures: list[str] = []
        AsserterException._compare_type(expected_exception, actual_exception, assertion_failures)
        AsserterException._compare_message_phrases(expected_exception, actual_exception, assertion_failures)
        AsserterException._compare_contextual_data(expected_exception, actual_exception, assertion_failures)
        AsserterException._compare_cause(expected_exception, actual_exception, assertion_failures)
        assert not assertion_failures, "EXCEPTION ASSERTION FAILED\n" + "\n".join(assertion_failures)

    @staticmethod
    def _compare_type(expected_exception: ExpectedException, actual_exception: BaseException, assertion_failures: list[str]) -> None:
        if type(actual_exception) is not expected_exception.exception_type:
            assertion_failures.append(f"type: expected {expected_exception.exception_type.__name__} but found {type(actual_exception).__name__}")

    @staticmethod
    def _compare_message_phrases(expected_exception: ExpectedException, actual_exception: BaseException, assertion_failures: list[str]) -> None:
        actual_message: str = str(actual_exception)
        assertion_failures.extend(
            f"message: expected the phrase {expected_phrase!r} in {actual_message!r}"
            for expected_phrase in expected_exception.message_phrases
            if expected_phrase not in actual_message
        )

    @staticmethod
    def _compare_contextual_data(expected_exception: ExpectedException, actual_exception: BaseException, assertion_failures: list[str]) -> None:
        if expected_exception.contextual_data_by_name is None:
            return
        if not isinstance(actual_exception, ContextualExceptionProtocol):
            assertion_failures.append("contextual data: expected some, but the exception carries none")
            return
        actual_contextual_data_by_name: dict[str, object] = {
            actual_name: actual_value
            for actual_name, actual_value in actual_exception.contextual_data_by_name.items()
            if actual_name != _MESSAGE_ENTRY_NAME
        }
        for expected_name, expected_value in expected_exception.contextual_data_by_name.items():
            if expected_name not in actual_contextual_data_by_name:
                assertion_failures.append(f"contextual data '{expected_name}' is missing; expected {expected_value!r}")
            elif actual_contextual_data_by_name[expected_name] != expected_value:
                assertion_failures.append(
                    f"contextual data '{expected_name}': expected {expected_value!r} but found {actual_contextual_data_by_name[expected_name]!r}"
                )
        assertion_failures.extend(
            f"contextual data '{actual_name}' was not expected"
            for actual_name in actual_contextual_data_by_name
            if actual_name not in expected_exception.contextual_data_by_name
        )

    @staticmethod
    def _compare_cause(expected_exception: ExpectedException, actual_exception: BaseException, assertion_failures: list[str]) -> None:
        if expected_exception.cause_type is None:
            return
        if type(actual_exception.__cause__) is not expected_exception.cause_type:
            assertion_failures.append(
                f"cause: expected {expected_exception.cause_type.__name__} but found {type(actual_exception.__cause__).__name__}"
            )
