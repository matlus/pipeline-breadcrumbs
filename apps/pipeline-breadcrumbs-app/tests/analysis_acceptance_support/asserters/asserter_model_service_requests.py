from collections.abc import Sequence

from analysis_acceptance_support.mediator_model_service import CapturedSectionDetectionRequest, CapturedSectionRequest, TestMediatorModelService


class AsserterModelServiceRequests:
    """Checks what the gateway put on the wire to the model service, as the Test Mediator received it."""

    @staticmethod
    def assert_requests(
        expected_detection_requests: Sequence[CapturedSectionDetectionRequest],
        expected_score_requests: Sequence[CapturedSectionRequest],
        expected_reconcile_requests: Sequence[CapturedSectionRequest],
        actual_test_mediator_model_service: TestMediatorModelService,
    ) -> None:
        assertion_failures: list[str] = []
        # Detection runs concurrently, so its requests arrive in any order; the other steps ask one section at a time, in order.
        actual_detection_requests: list[CapturedSectionDetectionRequest] = sorted(
            actual_test_mediator_model_service.captured_detection_requests, key=lambda actual_request: actual_request["page_number"]
        )
        AsserterModelServiceRequests._compare("detection", list(expected_detection_requests), actual_detection_requests, assertion_failures)
        AsserterModelServiceRequests._compare(
            "score", list(expected_score_requests), actual_test_mediator_model_service.captured_score_requests, assertion_failures
        )
        AsserterModelServiceRequests._compare(
            "reconcile", list(expected_reconcile_requests), actual_test_mediator_model_service.captured_reconcile_requests, assertion_failures
        )
        assert not assertion_failures, "MODEL SERVICE REQUESTS ASSERTION FAILED\n" + "\n".join(assertion_failures)

    @staticmethod
    def assert_detection_concurrency(
        expected_page_numbers: Sequence[int], expected_maximum_concurrent_count: int, actual_test_mediator_model_service: TestMediatorModelService
    ) -> None:
        assertion_failures: list[str] = []
        actual_page_numbers: list[int] = sorted(
            actual_request["page_number"] for actual_request in actual_test_mediator_model_service.captured_detection_requests
        )
        if actual_page_numbers != list(expected_page_numbers):
            assertion_failures.append(f"pages asked about: expected {list(expected_page_numbers)} but found {actual_page_numbers}")
        if actual_test_mediator_model_service.maximum_concurrent_detection_count != expected_maximum_concurrent_count:
            assertion_failures.append(
                f"most requests at once: expected {expected_maximum_concurrent_count} "
                f"but found {actual_test_mediator_model_service.maximum_concurrent_detection_count}"
            )
        assert not assertion_failures, "DETECTION CONCURRENCY ASSERTION FAILED\n" + "\n".join(assertion_failures)

    @staticmethod
    def _compare[CapturedRequestT](
        request_kind: str, expected_requests: list[CapturedRequestT], actual_requests: list[CapturedRequestT], assertion_failures: list[str]
    ) -> None:
        if actual_requests != expected_requests:
            assertion_failures.append(f"{request_kind} requests:\n  expected {expected_requests}\n  actual   {actual_requests}")
