import asyncio
import json
import unicodedata
from types import TracebackType
from typing import Any, Final, Self, TypedDict, cast, final

import httpx

from pipeline_breadcrumbs_app.document_analysis.exceptions import (
    ModelServiceContractException,
    ModelServiceRequestRejectedException,
    ModelServiceUnavailableException,
)
from pipeline_breadcrumbs_app.document_analysis.models import ClassificationPrompt

DETECT_SECTION_OPERATION: Final[str] = "detect_section"
SCORE_SECTION_OPERATION: Final[str] = "score_section"
RECONCILE_SECTION_OPERATION: Final[str] = "reconcile_section"


class SectionDetectionRequestResource(TypedDict):
    """The wire shape of a detection question."""

    page_number: int
    page_text: str


class SectionQuestionRequestResource(TypedDict):
    """The wire shape of a score or reconciliation question about one section."""

    page_number: int
    title: str
    text: str


@final
class GatewayModelService:
    # Asks the model service the system's three questions over its HTTP API. Each answer is the model's
    # raw reply: untrusted text that the processors parse and check, so the gateway never interprets it.
    #
    # The API, owned by the team that runs the model:
    #   POST /section-detections       {"page_number", "page_text"}   -> {"reply": "<raw model text>"}
    #   POST /section-scores           {"page_number", "title", "text"} -> {"reply": ...}
    #   POST /section-reconciliations  {"page_number", "title", "text"} -> {"reply": ...}
    #
    # Long-lived and manager-owned: the HTTP client pools connections across calls, and constructing it
    # performs no I/O, so building the system never depends on the model service being reachable.
    #
    # The transport comes from the service locator. Production supplies the network transport, the demo
    # an in-process simulation of the service, and tests their Test Mediator, so this class runs for real
    # everywhere: request building, response checking and exception translation are always these code paths.
    #
    # Nothing is retried. A failed call fails its step, and the step's breadcrumbs say where; a host that
    # wants retries owns that policy, because only it knows what a repeated model call costs.

    SECTION_DETECTIONS_PATH: Final[str] = "/section-detections"
    SECTION_SCORES_PATH: Final[str] = "/section-scores"
    SECTION_RECONCILIATIONS_PATH: Final[str] = "/section-reconciliations"
    REPLY_FIELD_NAME: Final[str] = "reply"
    # Bodies are read raw so their size can be bounded, so the service must not compress them.
    IDENTITY_ENCODING_HEADERS: Final[dict[str, str]] = {"Accept-Encoding": "identity"}

    # Model calls are slow; a minute bounds one call, including a body that arrives slowly.
    REQUEST_TIMEOUT_SECONDS: Final[float] = 60.0
    HTTP_STATUS_TOO_MANY_REQUESTS: Final[int] = 429
    HTTP_STATUS_SERVER_ERROR_FLOOR: Final[int] = 500
    # Bodies are read with a bound, so a misbehaving service cannot exhaust memory or flood the logs.
    MAXIMUM_REPLY_ENVELOPE_BYTES: Final[int] = 1_048_576
    MAXIMUM_FAILURE_DETAIL_BYTES: Final[int] = 2048

    def __init__(self, base_url: str, http_transport: httpx.AsyncBaseTransport) -> None:
        self._http_client: httpx.AsyncClient = httpx.AsyncClient(base_url=base_url, transport=http_transport, timeout=self.REQUEST_TIMEOUT_SECONDS)

    async def detect_section(self, page_number: int, page_text: str) -> str:
        section_detection_request_resource: SectionDetectionRequestResource = {"page_number": page_number, "page_text": page_text}
        return await self._ask(DETECT_SECTION_OPERATION, self.SECTION_DETECTIONS_PATH, section_detection_request_resource)

    async def score_section(self, classification_prompt: ClassificationPrompt) -> str:
        return await self._ask(SCORE_SECTION_OPERATION, self.SECTION_SCORES_PATH, self._to_section_question(classification_prompt))

    async def reconcile_section(self, classification_prompt: ClassificationPrompt) -> str:
        return await self._ask(RECONCILE_SECTION_OPERATION, self.SECTION_RECONCILIATIONS_PATH, self._to_section_question(classification_prompt))

    async def close(self) -> None:
        # Idempotent without state of its own: the client already knows whether it is closed.
        if not self._http_client.is_closed:
            await self._http_client.aclose()

    async def __aenter__(self) -> Self:
        # Entry acquires nothing: the client exists from construction and performs no I/O until a call.
        return self

    async def __aexit__(self, _exc_type: type[BaseException] | None, _exc: BaseException | None, _traceback: TracebackType | None) -> None:
        await self.close()

    async def _ask(
        self, operation_name: str, resource_path: str, request_resource: SectionDetectionRequestResource | SectionQuestionRequestResource
    ) -> str:
        failed_status_code: int | None = None
        try:
            # HTTPX's read timeout applies per read; bound the whole call too, so a slowly dribbling body cannot stretch it.
            async with (
                asyncio.timeout(self.REQUEST_TIMEOUT_SECONDS),
                self._http_client.stream(
                    "POST", resource_path, json=request_resource, headers=self.IDENTITY_ENCODING_HEADERS
                ) as model_service_response,
            ):
                if not model_service_response.is_success:
                    failed_status_code = model_service_response.status_code
                    failure_detail: str = await self._read_failure_detail(model_service_response)
                    raise self._create_status_error(operation_name, model_service_response.status_code, failure_detail)
                reply_envelope_bytes: bytes = await self._read_bounded(model_service_response, self.MAXIMUM_REPLY_ENVELOPE_BYTES + 1)
        except (httpx.TransportError, OSError, TimeoutError) as transport_error:
            if failed_status_code is not None:
                # The service already answered with a failure status; running out of time reading its detail must not hide that answer.
                raise self._create_status_error(
                    operation_name, failed_status_code, "the failure detail could not be read in time"
                ) from transport_error
            raise ModelServiceUnavailableException(
                operation_name, self._sanitize(f"{type(transport_error).__name__}: {transport_error}")
            ) from transport_error
        return self._extract_reply(operation_name, reply_envelope_bytes)

    @classmethod
    def _create_status_error(
        cls, operation_name: str, http_status_code: int, failure_detail: str
    ) -> ModelServiceUnavailableException | ModelServiceRequestRejectedException:
        # 429 and 5xx are the service's trouble and may pass; any other refusal will be refused again.
        if http_status_code == cls.HTTP_STATUS_TOO_MANY_REQUESTS or http_status_code >= cls.HTTP_STATUS_SERVER_ERROR_FLOOR:
            return ModelServiceUnavailableException(operation_name, failure_detail, http_status_code)
        return ModelServiceRequestRejectedException(operation_name, http_status_code, failure_detail)

    @classmethod
    def _extract_reply(cls, operation_name: str, reply_envelope_bytes: bytes) -> str:
        if len(reply_envelope_bytes) > cls.MAXIMUM_REPLY_ENVELOPE_BYTES:
            raise ModelServiceContractException(operation_name, f"the response is larger than {cls.MAXIMUM_REPLY_ENVELOPE_BYTES} bytes")
        try:
            reply_envelope: Any = json.loads(reply_envelope_bytes)
        except (ValueError, RecursionError) as decode_error:
            raise ModelServiceContractException(operation_name, f"the response is not JSON ({type(decode_error).__name__})") from decode_error
        reply: Any = cast("dict[str, Any]", reply_envelope).get(cls.REPLY_FIELD_NAME) if isinstance(reply_envelope, dict) else None
        if not isinstance(reply, str):
            raise ModelServiceContractException(operation_name, f"the response is not a JSON object with a text '{cls.REPLY_FIELD_NAME}' field")
        return reply

    @classmethod
    async def _read_failure_detail(cls, model_service_response: httpx.Response) -> str:
        # Best effort: the status has already classified the failure, so an unreadable body must not reclassify it.
        try:
            failure_body: bytes = await cls._read_bounded(model_service_response, cls.MAXIMUM_FAILURE_DETAIL_BYTES)
        except (httpx.TransportError, OSError) as transport_error:
            return f"(the response body could not be read: {type(transport_error).__name__})"
        return cls._sanitize(failure_body.decode("utf-8", errors="replace")) or "(no response body)"

    @staticmethod
    async def _read_bounded(model_service_response: httpx.Response, maximum_byte_count: int) -> bytes:
        # A custom transport can hand back an already-loaded response; its content is read without consuming the stream twice.
        if model_service_response.is_stream_consumed:
            return model_service_response.content[:maximum_byte_count]
        response_prefix: bytearray = bytearray()
        response_chunk: bytes
        async for response_chunk in model_service_response.aiter_raw():
            response_prefix.extend(response_chunk[: maximum_byte_count - len(response_prefix)])
            if len(response_prefix) >= maximum_byte_count:
                break
        return bytes(response_prefix)

    @staticmethod
    def _sanitize(raw_detail: str) -> str:
        # Control and format characters could forge log lines; they become spaces before the detail reaches an exception.
        return "".join(" " if unicodedata.category(character).startswith("C") else character for character in raw_detail).strip()

    @staticmethod
    def _to_section_question(classification_prompt: ClassificationPrompt) -> SectionQuestionRequestResource:
        return {"page_number": classification_prompt.page_number, "title": classification_prompt.title, "text": classification_prompt.text}
