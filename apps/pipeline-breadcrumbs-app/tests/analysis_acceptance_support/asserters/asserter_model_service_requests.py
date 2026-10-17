from collections.abc import Sequence
from typing import Final

from breadcrumbs_acceptance_support.assertion_reports import format_assertion_report

from analysis_acceptance_support.mediator_model_service import SectionDetectionRequest, SectionQuestionRequest


class ModelServiceRequestsAsserter:
    """Checks what the gateway put on the wire to the model service, as the test gathered it from the Test Mediator."""

    MODEL_SERVICE_REQUESTS_ASSERTION_FAILED_HEADER: Final[str] = "MODEL SERVICE REQUESTS ASSERTION FAILED"

    @staticmethod
    def assert_expected_and_actual_are_equal(
        expected_section_detection_requests: Sequence[SectionDetectionRequest],
        expected_score_section_question_requests: Sequence[SectionQuestionRequest],
        expected_reconcile_section_question_requests: Sequence[SectionQuestionRequest],
        actual_section_detection_requests: Sequence[SectionDetectionRequest],
        actual_score_section_question_requests: Sequence[SectionQuestionRequest],
        actual_reconcile_section_question_requests: Sequence[SectionQuestionRequest],
    ) -> None:
        # Detection runs concurrently, so its requests arrive in any order; the other steps ask one section at a time, in order.
        actual_section_detection_requests_in_page_order: list[SectionDetectionRequest] = sorted(
            actual_section_detection_requests, key=lambda actual_section_detection_request: actual_section_detection_request["page_number"]
        )
        mismatches: list[str] = [
            *ModelServiceRequestsAsserter._compare("detection", expected_section_detection_requests, actual_section_detection_requests_in_page_order),
            *ModelServiceRequestsAsserter._compare("score", expected_score_section_question_requests, actual_score_section_question_requests),
            *ModelServiceRequestsAsserter._compare(
                "reconcile", expected_reconcile_section_question_requests, actual_reconcile_section_question_requests
            ),
        ]
        assert not mismatches, format_assertion_report(
            ModelServiceRequestsAsserter.MODEL_SERVICE_REQUESTS_ASSERTION_FAILED_HEADER,
            "The gateway asks the model service exactly what each step needs, and nothing more.",
            f"received {len(actual_section_detection_requests)} detection, {len(actual_score_section_question_requests)} score, "
            f"{len(actual_reconcile_section_question_requests)} reconcile",
            mismatches,
        )

    @staticmethod
    def _compare[ModelServiceRequestT: (SectionDetectionRequest, SectionQuestionRequest)](
        request_kind: str,
        expected_model_service_requests: Sequence[ModelServiceRequestT],
        actual_model_service_requests: Sequence[ModelServiceRequestT],
    ) -> list[str]:
        mismatches: list[str] = []
        position: int
        expected_model_service_request: ModelServiceRequestT
        actual_model_service_request: ModelServiceRequestT
        for position, (expected_model_service_request, actual_model_service_request) in enumerate(
            zip(expected_model_service_requests, actual_model_service_requests, strict=False)
        ):
            field_name: str
            for field_name in sorted(set(expected_model_service_request) | set(actual_model_service_request)):
                expected_value: object = expected_model_service_request.get(field_name)
                actual_value: object = actual_model_service_request.get(field_name)
                if actual_value != expected_value:
                    mismatches.append(f"{request_kind} request {position} '{field_name}': expected {expected_value!r} but found {actual_value!r}")
        mismatches.extend(
            f"{request_kind} request {position}: missing {missing_request!r}"
            for position, missing_request in enumerate(
                expected_model_service_requests[len(actual_model_service_requests) :], len(actual_model_service_requests)
            )
        )
        mismatches.extend(
            f"{request_kind} request {position}: unexpected {unexpected_request!r}"
            for position, unexpected_request in enumerate(
                actual_model_service_requests[len(expected_model_service_requests) :], len(expected_model_service_requests)
            )
        )
        return mismatches


class DetectionConcurrencyAsserter:
    """Checks that section detection asked about every page while holding no more requests open at once than the configured limit."""

    DETECTION_CONCURRENCY_ASSERTION_FAILED_HEADER: Final[str] = "DETECTION CONCURRENCY ASSERTION FAILED"

    @staticmethod
    def assert_expected_and_actual_are_equal(
        expected_page_numbers: Sequence[int],
        expected_maximum_concurrent_count: int,
        actual_section_detection_requests: Sequence[SectionDetectionRequest],
        actual_maximum_concurrent_detection_count: int,
    ) -> None:
        mismatches: list[str] = []
        actual_page_numbers: list[int] = sorted(
            actual_section_detection_request["page_number"] for actual_section_detection_request in actual_section_detection_requests
        )
        if actual_page_numbers != list(expected_page_numbers):
            mismatches.append(f"pages asked about: expected {list(expected_page_numbers)} but found {actual_page_numbers}")
        if actual_maximum_concurrent_detection_count != expected_maximum_concurrent_count:
            mismatches.append(
                f"most requests at once: expected {expected_maximum_concurrent_count} but found {actual_maximum_concurrent_detection_count}"
            )
        assert not mismatches, format_assertion_report(
            DetectionConcurrencyAsserter.DETECTION_CONCURRENCY_ASSERTION_FAILED_HEADER,
            "Detection asks about every page, and never holds more requests open at once than the configured limit.",
            f"{len(expected_page_numbers)} page(s), limit {expected_maximum_concurrent_count}",
            mismatches,
        )
