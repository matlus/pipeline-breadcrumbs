import logging
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field

_MISSING: object = object()


@dataclass(frozen=True)
class ExpectedLogRecord:
    message: str | None = None
    message_suffix: str | None = None
    level: int | None = None
    attribute_value_by_key: Mapping[str, object] = field(default_factory=dict[str, object])
    absent_attribute_keys: Sequence[str] = field(default_factory=tuple[str, ...])
    carries_traceback: bool | None = None


class AsserterLogRecord:
    """Checks one log record's message, level, attributes and traceback, reporting every difference at once."""

    @staticmethod
    def assert_record(expected_log_record: ExpectedLogRecord, actual_log_record: logging.LogRecord) -> None:
        assertion_failures: list[str] = []
        actual_message: str = actual_log_record.getMessage()
        if expected_log_record.message is not None and actual_message != expected_log_record.message:
            assertion_failures.append(f"message: expected {expected_log_record.message!r} but found {actual_message!r}")
        if expected_log_record.message_suffix is not None and not actual_message.endswith(expected_log_record.message_suffix):
            assertion_failures.append(f"message: expected it to end with {expected_log_record.message_suffix!r} but found {actual_message!r}")
        if expected_log_record.level is not None and actual_log_record.levelno != expected_log_record.level:
            assertion_failures.append(
                f"level: expected {logging.getLevelName(expected_log_record.level)} but found {logging.getLevelName(actual_log_record.levelno)}"
            )
        AsserterLogRecord._compare_attributes(expected_log_record.attribute_value_by_key, actual_log_record, assertion_failures)
        assertion_failures.extend(
            f"attribute {absent_key!r}: expected none but found {actual_log_record.__dict__[absent_key]!r}"
            for absent_key in expected_log_record.absent_attribute_keys
            if absent_key in actual_log_record.__dict__
        )
        if expected_log_record.carries_traceback is not None and (actual_log_record.exc_info is not None) != expected_log_record.carries_traceback:
            assertion_failures.append(f"traceback: expected {'one' if expected_log_record.carries_traceback else 'none'}")
        assert not assertion_failures, "LOG RECORD ASSERTION FAILED\n" + "\n".join(assertion_failures)

    @staticmethod
    def assert_every_record_carries(expected_attribute_value_by_key: Mapping[str, object], actual_log_records: Sequence[logging.LogRecord]) -> None:
        assert actual_log_records, "LOG RECORD ASSERTION FAILED\nexpected records but none were logged"
        assertion_failures: list[str] = []
        for actual_log_record in actual_log_records:
            record_failures: list[str] = []
            AsserterLogRecord._compare_attributes(expected_attribute_value_by_key, actual_log_record, record_failures)
            assertion_failures.extend(f"{actual_log_record.getMessage()!r}: {record_failure}" for record_failure in record_failures)
        assert not assertion_failures, "LOG RECORD ASSERTION FAILED\n" + "\n".join(assertion_failures)

    @staticmethod
    def _compare_attributes(
        expected_attribute_value_by_key: Mapping[str, object], actual_log_record: logging.LogRecord, assertion_failures: list[str]
    ) -> None:
        for expected_key, expected_value in expected_attribute_value_by_key.items():
            actual_value: object = actual_log_record.__dict__.get(expected_key, _MISSING)
            if actual_value is _MISSING:
                assertion_failures.append(f"attribute {expected_key!r}: missing; expected {expected_value!r}")
            elif actual_value != expected_value:
                assertion_failures.append(f"attribute {expected_key!r}: expected {expected_value!r} but found {actual_value!r}")
