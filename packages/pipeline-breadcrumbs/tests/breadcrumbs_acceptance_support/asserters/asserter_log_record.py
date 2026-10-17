import logging
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Final

from breadcrumbs_acceptance_support.assertion_reports import format_assertion_report

_MISSING: Final[object] = object()


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

    LOG_RECORD_ASSERTION_FAILED_HEADER: Final[str] = "LOG RECORD ASSERTION FAILED"

    @staticmethod
    def assert_record(expected_log_record: ExpectedLogRecord, actual_log_record: logging.LogRecord) -> None:
        actual_message: str = actual_log_record.getMessage()
        mismatches: list[str] = []
        if expected_log_record.message is not None and actual_message != expected_log_record.message:
            mismatches.append(f"message: expected {expected_log_record.message!r} but found {actual_message!r}")
        if expected_log_record.message_suffix is not None and not actual_message.endswith(expected_log_record.message_suffix):
            mismatches.append(f"message: expected it to end with {expected_log_record.message_suffix!r}")
        if expected_log_record.level is not None and actual_log_record.levelno != expected_log_record.level:
            mismatches.append(
                f"level: expected {logging.getLevelName(expected_log_record.level)} but found {logging.getLevelName(actual_log_record.levelno)}"
            )
        mismatches.extend(AsserterLogRecord._compare_attributes(expected_log_record.attribute_value_by_key, actual_log_record))
        mismatches.extend(
            f"attribute {absent_key!r}: expected none but found {actual_log_record.__dict__[absent_key]!r}"
            for absent_key in expected_log_record.absent_attribute_keys
            if absent_key in actual_log_record.__dict__
        )
        if expected_log_record.carries_traceback is not None and (actual_log_record.exc_info is not None) != expected_log_record.carries_traceback:
            mismatches.append(f"traceback: expected {'one' if expected_log_record.carries_traceback else 'none'}")
        assert not mismatches, format_assertion_report(
            AsserterLogRecord.LOG_RECORD_ASSERTION_FAILED_HEADER,
            "The record says what happened and carries the attributes a reader filters by.",
            f"record {actual_message!r}",
            mismatches,
        )

    @staticmethod
    def assert_every_record_carries(expected_attribute_value_by_key: Mapping[str, object], actual_log_records: Sequence[logging.LogRecord]) -> None:
        mismatches: list[str] = [] if actual_log_records else ["expected records, but none were logged"]
        for actual_log_record in actual_log_records:
            mismatches.extend(
                f"{actual_log_record.getMessage()!r}: {attribute_mismatch}"
                for attribute_mismatch in AsserterLogRecord._compare_attributes(expected_attribute_value_by_key, actual_log_record)
            )
        assert not mismatches, format_assertion_report(
            AsserterLogRecord.LOG_RECORD_ASSERTION_FAILED_HEADER,
            "Every record the run writes carries the run-wide attributes.",
            f"{len(actual_log_records)} record(s) checked for {sorted(expected_attribute_value_by_key)}",
            mismatches,
        )

    @staticmethod
    def _compare_attributes(expected_attribute_value_by_key: Mapping[str, object], actual_log_record: logging.LogRecord) -> list[str]:
        attribute_mismatches: list[str] = []
        expected_key: str
        expected_value: object
        for expected_key, expected_value in expected_attribute_value_by_key.items():
            actual_value: object = actual_log_record.__dict__.get(expected_key, _MISSING)
            if actual_value is _MISSING:
                attribute_mismatches.append(f"attribute {expected_key!r}: missing; expected {expected_value!r}")
            elif actual_value != expected_value:
                attribute_mismatches.append(f"attribute {expected_key!r}: expected {expected_value!r} but found {actual_value!r}")
        return attribute_mismatches
