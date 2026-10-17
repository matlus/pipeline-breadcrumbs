from collections.abc import Set as AbstractSet
from typing import Final

from breadcrumbs_acceptance_support.assertion_reports import format_assertion_report


class AsserterSharedLogger:
    """Checks that a logger the caller lent to the system carried the system's records and came back as it was lent."""

    SHARED_LOGGER_ASSERTION_FAILED_HEADER: Final[str] = "SHARED LOGGER ASSERTION FAILED"

    @staticmethod
    def assert_logger_shared_and_restored(
        expected_levels: AbstractSet[int], expected_handler_count: int, actual_levels: AbstractSet[int], actual_handler_count: int
    ) -> None:
        mismatches: list[str] = []
        missing_levels: list[int] = sorted(expected_levels - actual_levels)
        if missing_levels:
            mismatches.append(f"records: expected levels {sorted(expected_levels)} but these never arrived {missing_levels}")
        if actual_handler_count != expected_handler_count:
            mismatches.append(f"handlers: expected {expected_handler_count} once the run finished but found {actual_handler_count}")
        assert not mismatches, format_assertion_report(
            AsserterSharedLogger.SHARED_LOGGER_ASSERTION_FAILED_HEADER,
            "The system logs through the caller's logger and leaves its handlers exactly as it found them.",
            f"records at levels {sorted(actual_levels)}, {actual_handler_count} handler(s) after the run",
            mismatches,
        )
