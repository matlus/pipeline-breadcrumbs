import asyncio
import json
from collections.abc import Callable, Coroutine, Mapping
from dataclasses import dataclass
from typing import ClassVar, Final, TypedDict, cast, override

import httpx

HTTP_STATUS_OK: Final[int] = 200
HTTP_STATUS_BAD_REQUEST: Final[int] = 400
HTTP_STATUS_SERVICE_UNAVAILABLE: Final[int] = 503

_SECTION_DETECTIONS_PATH: Final[str] = "/section-detections"
_SECTION_SCORES_PATH: Final[str] = "/section-scores"
_SECTION_RECONCILIATIONS_PATH: Final[str] = "/section-reconciliations"


class SectionDetectionRequest(TypedDict):
    """One detection request exactly as the gateway put it on the wire."""

    page_number: int
    page_text: str


class SectionQuestionRequest(TypedDict):
    """One score or reconciliation request exactly as the gateway put it on the wire (mirrors ClassificationPrompt)."""

    page_number: int
    title: str
    text: str


# One scripted answer that replaces the model's reply: a failure status, or a success that breaks the API's envelope. State only.
@dataclass(frozen=True)
class ScriptedModelServiceResponse:
    status_code: int
    body_text: str


class _MockTransportClosingSpy(httpx.MockTransport):
    """The in-process transport, which also reports each time the gateway closes it."""

    def __init__(self, answer_request: Callable[[httpx.Request], Coroutine[None, None, httpx.Response]], record_closed: Callable[[], None]) -> None:
        super().__init__(answer_request)
        self._record_closed: Callable[[], None] = record_closed

    @override
    async def aclose(self) -> None:
        self._record_closed()


class TestMediatorModelService:
    # The Test Mediator/Spy for the model service's HTTP API.
    #
    # Terminates the gateway's calls at the HTTP transport, in-process: no port, no stub process, safe to
    # run in parallel. The gateway above it runs for real - request building, response checking and
    # exception translation are always production code paths; only the wire is swapped (through
    # ServiceLocatorTesting).
    #
    # Two-way conversation. Going in, the test scripts what the model replies: detections by page
    # number, scores and reconciliations by title, or one response that replaces every reply (a failure
    # status, or a body that breaks the API's envelope), or an unreachable service. Coming out, it hands
    # back every request that reached it, the most detection requests it ever held at once, and how many
    # times the gateway closed the wire.
    #
    # A request is captured only if it reached the service: a scripted failure status captures (the
    # service saw it and refused), simulated unreachability does not (nothing arrived).

    # Not a test class despite the Test* name - this tells pytest not to collect it.
    __test__: ClassVar[bool] = False

    def __init__(
        self,
        *,
        detection_reply_by_page_number: Mapping[int, str] | None = None,
        score_reply_by_title: Mapping[str, str] | None = None,
        reconcile_reply_by_title: Mapping[str, str] | None = None,
        scripted_model_service_response: ScriptedModelServiceResponse | None = None,
        simulate_unreachable: bool = False,
    ) -> None:
        self._detection_reply_by_page_number: Mapping[int, str] = detection_reply_by_page_number or {}
        self._score_reply_by_title: Mapping[str, str] = score_reply_by_title or {}
        self._reconcile_reply_by_title: Mapping[str, str] = reconcile_reply_by_title or {}
        self._scripted_model_service_response: ScriptedModelServiceResponse | None = scripted_model_service_response
        self._simulate_unreachable: bool = simulate_unreachable
        self._concurrent_detection_count: int = 0
        self.captured_section_detection_requests: list[SectionDetectionRequest] = []
        self.captured_score_section_question_requests: list[SectionQuestionRequest] = []
        self.captured_reconcile_section_question_requests: list[SectionQuestionRequest] = []
        self.maximum_concurrent_detection_count: int = 0
        self.closed_transport_count: int = 0

    @property
    def captured_model_service_request_count(self) -> int:
        return (
            len(self.captured_section_detection_requests)
            + len(self.captured_score_section_question_requests)
            + len(self.captured_reconcile_section_question_requests)
        )

    def create_http_transport(self) -> httpx.MockTransport:
        return _MockTransportClosingSpy(self._answer_model_service_request, self._record_transport_closed)

    def _record_transport_closed(self) -> None:
        self.closed_transport_count += 1

    async def _answer_model_service_request(self, model_service_request: httpx.Request) -> httpx.Response:
        if self._simulate_unreachable:
            raise httpx.ConnectError("the model service is unreachable (simulated by TestMediatorModelService)")
        resource_path: str = model_service_request.url.path
        if resource_path == _SECTION_DETECTIONS_PATH:
            return await self._answer_detection(cast(SectionDetectionRequest, json.loads(model_service_request.content)))
        captured_section_question_request: SectionQuestionRequest = cast(SectionQuestionRequest, json.loads(model_service_request.content))
        if resource_path == _SECTION_SCORES_PATH:
            self.captured_score_section_question_requests.append(captured_section_question_request)
            return self._answer(self._score_reply_by_title, captured_section_question_request["title"])
        if resource_path == _SECTION_RECONCILIATIONS_PATH:
            self.captured_reconcile_section_question_requests.append(captured_section_question_request)
            return self._answer(self._reconcile_reply_by_title, captured_section_question_request["title"])
        raise AssertionError(f"The gateway called a resource the model service does not have: {resource_path}")

    async def _answer_detection(self, captured_section_detection_request: SectionDetectionRequest) -> httpx.Response:
        self.captured_section_detection_requests.append(captured_section_detection_request)
        self._concurrent_detection_count += 1
        self.maximum_concurrent_detection_count = max(self.maximum_concurrent_detection_count, self._concurrent_detection_count)
        try:
            # Yield to the event loop so concurrent requests overlap here, where the count can see them.
            await asyncio.sleep(0)
            return self._answer(self._detection_reply_by_page_number, captured_section_detection_request["page_number"])
        finally:
            self._concurrent_detection_count -= 1

    def _answer[QuestionSubjectT](
        self, reply_by_question_subject: Mapping[QuestionSubjectT, str], question_subject: QuestionSubjectT
    ) -> httpx.Response:
        if self._scripted_model_service_response is not None:
            return httpx.Response(self._scripted_model_service_response.status_code, text=self._scripted_model_service_response.body_text)
        if question_subject not in reply_by_question_subject:
            raise AssertionError(f"The scenario arranged no model reply for {question_subject!r}")
        return httpx.Response(HTTP_STATUS_OK, json={"reply": reply_by_question_subject[question_subject]})
