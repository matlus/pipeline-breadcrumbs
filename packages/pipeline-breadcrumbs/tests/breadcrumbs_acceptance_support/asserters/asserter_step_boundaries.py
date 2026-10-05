import logging
from collections.abc import Sequence
from dataclasses import dataclass

from pipeline_breadcrumbs import AttributeKey, EventKind
from pipeline_breadcrumbs.testing import RecordCapture


@dataclass(frozen=True)
class ExpectedStepBoundary:
    step_number: str
    step_status: str
    elapsed_seconds: float | None = None


class AsserterStepBoundaries:
    """Checks the step boundary records a run logged, in order, and reports every discrepancy at once."""

    @staticmethod
    def assert_exactly_these_step_boundaries(
        expected_step_boundaries: Sequence[ExpectedStepBoundary],
        actual_log_records: Sequence[logging.LogRecord],
    ) -> None:
        actual_step_boundaries: list[ExpectedStepBoundary] = AsserterStepBoundaries._gather_step_boundaries(actual_log_records)
        assertion_failures: list[str] = []
        if len(actual_step_boundaries) != len(expected_step_boundaries):
            assertion_failures.append(f"expected {len(expected_step_boundaries)} step boundaries but found {len(actual_step_boundaries)}")
        for position, (expected_step_boundary, actual_step_boundary) in enumerate(
            zip(expected_step_boundaries, actual_step_boundaries, strict=False)
        ):
            if expected_step_boundary.step_number != actual_step_boundary.step_number:
                assertion_failures.append(
                    f"boundary {position}: expected step {expected_step_boundary.step_number} but found {actual_step_boundary.step_number}"
                )
            if expected_step_boundary.step_status != actual_step_boundary.step_status:
                assertion_failures.append(
                    f"boundary {position}: expected status {expected_step_boundary.step_status} but found {actual_step_boundary.step_status}"
                )
            expected_elapsed_seconds: float | None = expected_step_boundary.elapsed_seconds
            if expected_elapsed_seconds is not None and expected_elapsed_seconds != actual_step_boundary.elapsed_seconds:
                assertion_failures.append(
                    f"boundary {position}: expected {expected_elapsed_seconds}s elapsed but found {actual_step_boundary.elapsed_seconds}s"
                )
        assert not assertion_failures, "STEP BOUNDARY ASSERTION FAILED\n" + "\n".join(assertion_failures)

    @staticmethod
    def _gather_step_boundaries(actual_log_records: Sequence[logging.LogRecord]) -> list[ExpectedStepBoundary]:
        actual_step_boundaries: list[ExpectedStepBoundary] = []
        for actual_log_record in actual_log_records:
            if RecordCapture.attribute(actual_log_record, AttributeKey.EVENT) != EventKind.STEP:
                continue
            actual_elapsed_seconds: object = RecordCapture.attribute(actual_log_record, AttributeKey.ELAPSED_SECONDS)
            actual_step_boundaries.append(
                ExpectedStepBoundary(
                    step_number=str(RecordCapture.attribute(actual_log_record, AttributeKey.STEP_NUMBER)),
                    step_status=str(RecordCapture.attribute(actual_log_record, AttributeKey.STATUS)),
                    elapsed_seconds=float(actual_elapsed_seconds) if isinstance(actual_elapsed_seconds, int | float) else None,
                )
            )
        return actual_step_boundaries
