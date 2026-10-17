import logging
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Final

from breadcrumbs_acceptance_support.assertion_reports import format_assertion_report
from pipeline_breadcrumbs import AttributeKey, EventKind
from pipeline_breadcrumbs.testing import RecordCapture


@dataclass(frozen=True)
class ExpectedStepBoundary:
    step_number: str
    step_status: str
    elapsed_seconds: float | None = None


class StepBoundariesAsserter:
    """Checks the step boundary records a run logged, in order, and reports every discrepancy at once."""

    STEP_BOUNDARIES_ASSERTION_FAILED_HEADER: Final[str] = "STEP BOUNDARY ASSERTION FAILED"

    @staticmethod
    def assert_expected_and_actual_are_equal(
        expected_step_boundaries: Sequence[ExpectedStepBoundary],
        actual_log_records: Sequence[logging.LogRecord],
    ) -> None:
        actual_step_boundaries: list[ExpectedStepBoundary] = StepBoundariesAsserter._to_step_boundaries(actual_log_records)
        mismatches: list[str] = []
        position: int
        expected_step_boundary: ExpectedStepBoundary
        actual_step_boundary: ExpectedStepBoundary
        for position, (expected_step_boundary, actual_step_boundary) in enumerate(
            zip(expected_step_boundaries, actual_step_boundaries, strict=False)
        ):
            mismatches.extend(StepBoundariesAsserter._compare_boundary(position, expected_step_boundary, actual_step_boundary))
        missing_expected_step_boundary: ExpectedStepBoundary
        for position, missing_expected_step_boundary in enumerate(
            expected_step_boundaries[len(actual_step_boundaries) :], start=len(actual_step_boundaries)
        ):
            mismatches.append(
                f"missing boundary {position}: step {missing_expected_step_boundary.step_number} {missing_expected_step_boundary.step_status}"
            )
        unexpected_actual_step_boundary: ExpectedStepBoundary
        for position, unexpected_actual_step_boundary in enumerate(
            actual_step_boundaries[len(expected_step_boundaries) :], start=len(expected_step_boundaries)
        ):
            mismatches.append(
                f"unexpected boundary {position}: step {unexpected_actual_step_boundary.step_number} {unexpected_actual_step_boundary.step_status}"
            )
        assert not mismatches, format_assertion_report(
            StepBoundariesAsserter.STEP_BOUNDARIES_ASSERTION_FAILED_HEADER,
            "Every step announces itself and reports how it ended, in the order the steps ran.",
            f"{len(expected_step_boundaries)} expected boundary record(s), {len(actual_step_boundaries)} logged",
            mismatches,
        )

    @staticmethod
    def _compare_boundary(position: int, expected_step_boundary: ExpectedStepBoundary, actual_step_boundary: ExpectedStepBoundary) -> list[str]:
        boundary_mismatches: list[str] = []
        if expected_step_boundary.step_number != actual_step_boundary.step_number:
            boundary_mismatches.append(
                f"boundary {position}: expected step {expected_step_boundary.step_number} but found {actual_step_boundary.step_number}"
            )
        if expected_step_boundary.step_status != actual_step_boundary.step_status:
            boundary_mismatches.append(
                f"boundary {position}: expected status {expected_step_boundary.step_status} but found {actual_step_boundary.step_status}"
            )
        expected_elapsed_seconds: float | None = expected_step_boundary.elapsed_seconds
        if expected_elapsed_seconds is not None and expected_elapsed_seconds != actual_step_boundary.elapsed_seconds:
            boundary_mismatches.append(
                f"boundary {position}: expected {expected_elapsed_seconds}s elapsed but found {actual_step_boundary.elapsed_seconds}s"
            )
        return boundary_mismatches

    @staticmethod
    def _to_step_boundaries(actual_log_records: Sequence[logging.LogRecord]) -> list[ExpectedStepBoundary]:
        actual_step_boundaries: list[ExpectedStepBoundary] = []
        for actual_log_record in actual_log_records:
            if actual_log_record.__dict__.get(AttributeKey.EVENT) != EventKind.STEP:
                continue
            actual_elapsed_seconds: object = actual_log_record.__dict__.get(AttributeKey.ELAPSED_SECONDS)
            actual_step_boundaries.append(
                ExpectedStepBoundary(
                    step_number=str(RecordCapture.attribute(actual_log_record, AttributeKey.STEP_NUMBER)),
                    step_status=str(RecordCapture.attribute(actual_log_record, AttributeKey.STATUS)),
                    elapsed_seconds=float(actual_elapsed_seconds) if isinstance(actual_elapsed_seconds, int | float) else None,
                )
            )
        return actual_step_boundaries
