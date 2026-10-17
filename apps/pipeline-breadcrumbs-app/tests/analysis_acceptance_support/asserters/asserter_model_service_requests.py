from collections.abc import Sequence
from typing import Final

from breadcrumbs_acceptance_support.assertion_reports import format_assertion_report

from analysis_acceptance_support.mediator_model_service import CapturedSectionDetectionRequest, CapturedSectionRequest


class AsserterModelServiceRequests:
    """Checks what the gateway put on the wire to the model service, as the test gathered it from the Test Mediator."""

    MODEL_SERVICE_REQUESTS_ASSERTION_FAILED_HEADER: Final[str] = "MODEL SERVICE REQUESTS ASSERTION FAILED"
    DETECTION_CONCURRENCY_ASSERTION_FAILED_HEADER: Final[str] = "DETECTION CONCURRENCY ASSERTION FAILED"

    @staticmethod
    def assert_requests(
        expected_detection_requests: Sequence[CapturedSectionDetectionRequest],
        expected_score_requests: Sequence[CapturedSectionRequest],
        expected_reconcile_requests: Sequence[CapturedSectionRequest],
        actual_detection_requests: Sequence[CapturedSectionDetectionRequest],
        actual_score_requests: Sequence[CapturedSectionRequest],
        actual_reconcile_requests: Sequence[CapturedSectionRequest],
    ) -> None:
        # Detection runs concurrently, so its requests arrive in any order; the other steps ask one section at a time, in order.
        actual_detection_requests_by_page: list[CapturedSectionDetectionRequest] = sorted(
            actual_detection_requests, key=lambda actual_detection_request: actual_detection_request["page_number"]
        )
        mismatches: list[str] = [
            *AsserterModelServiceRequests._compare("detection", expected_detection_requests, actual_detection_requests_by_page),
            *AsserterModelServiceRequests._compare("score", expected_score_requests, actual_score_requests),
            *AsserterModelServiceRequests._compare("reconcile", expected_reconcile_requests, actual_reconcile_requests),
        ]
        assert not mismatches, format_assertion_report(
            AsserterModelServiceRequests.MODEL_SERVICE_REQUESTS_ASSERTION_FAILED_HEADER,
            "The gateway asks the model service exactly what each step needs, and nothing more.",
            f"received {len(actual_detection_requests)} detection, {len(actual_score_requests)} score, {len(actual_reconcile_requests)} reconcile",
            mismatches,
        )

    @staticmethod
    def assert_detection_concurrency(
        expected_page_numbers: Sequence[int],
        expected_maximum_concurrent_count: int,
        actual_detection_requests: Sequence[CapturedSectionDetectionRequest],
        actual_maximum_concurrent_detection_count: int,
    ) -> None:
        mismatches: list[str] = []
        actual_page_numbers: list[int] = sorted(actual_detection_request["page_number"] for actual_detection_request in actual_detection_requests)
        if actual_page_numbers != list(expected_page_numbers):
            mismatches.append(f"pages asked about: expected {list(expected_page_numbers)} but found {actual_page_numbers}")
        if actual_maximum_concurrent_detection_count != expected_maximum_concurrent_count:
            mismatches.append(
                f"most requests at once: expected {expected_maximum_concurrent_count} but found {actual_maximum_concurrent_detection_count}"
            )
        assert not mismatches, format_assertion_report(
            AsserterModelServiceRequests.DETECTION_CONCURRENCY_ASSERTION_FAILED_HEADER,
            "Detection asks about every page, and never holds more requests open at once than the configured limit.",
            f"{len(expected_page_numbers)} page(s), limit {expected_maximum_concurrent_count}",
            mismatches,
        )

    @staticmethod
    def _compare[CapturedRequestT: (CapturedSectionDetectionRequest, CapturedSectionRequest)](
        request_kind: str, expected_requests: Sequence[CapturedRequestT], actual_requests: Sequence[CapturedRequestT]
    ) -> list[str]:
        mismatches: list[str] = []
        position: int
        expected_request: CapturedRequestT
        actual_request: CapturedRequestT
        for position, (expected_request, actual_request) in enumerate(zip(expected_requests, actual_requests, strict=False)):
            field_name: str
            for field_name in expected_request:
                expected_value: object = expected_request.get(field_name)
                actual_value: object = actual_request.get(field_name)
                if actual_value != expected_value:
                    mismatches.append(f"{request_kind} request {position} '{field_name}': expected {expected_value!r} but found {actual_value!r}")
        mismatches.extend(
            f"{request_kind} request {position}: missing {missing_request!r}"
            for position, missing_request in enumerate(expected_requests[len(actual_requests) :], len(actual_requests))
        )
        mismatches.extend(
            f"{request_kind} request {position}: unexpected {unexpected_request!r}"
            for position, unexpected_request in enumerate(actual_requests[len(expected_requests) :], len(expected_requests))
        )
        return mismatches
