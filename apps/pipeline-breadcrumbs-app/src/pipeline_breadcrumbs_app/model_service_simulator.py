"""An in-process stand-in for the model service, so the demo runs offline and reads the same every time.

It answers the model service's HTTP API at the transport, so the system's real gateway builds every
request and checks every response exactly as it would against the real service. No network, no API
key, no configuration. Every answer takes `latency_seconds`, the way a real model call takes time,
so the log appears at a believable pace.
"""

import asyncio
import json
from typing import Any, Final, final

import httpx

# A page containing this marker gets a chatty, non-JSON reply, to show how a failure looks.
# The fault travels in the input, so the simulator needs to know nothing about which document it serves.
MALFORMED_REPLY_MARKER: Final[str] = "[[demo: the model replies with malformed JSON for this page]]"

_SECTION_DETECTIONS_PATH: Final[str] = "/section-detections"
_SECTION_SCORES_PATH: Final[str] = "/section-scores"
_SECTION_RECONCILIATIONS_PATH: Final[str] = "/section-reconciliations"
_HTTP_STATUS_OK: Final[int] = 200
_HTTP_STATUS_NOT_FOUND: Final[int] = 404
_TITLE_FIELD: Final[str] = "title"
_CATEGORY_FIELD: Final[str] = "category"
_CONFIDENCE_FIELD: Final[str] = "confidence"

_AMBIGUOUS_TITLES: Final[frozenset[str]] = frozenset({"Miscellaneous", "General Provisions"})
_DEFAULT_CATEGORY: Final[str] = "General"
_UNTITLED_PAGE_TITLE: Final[str] = "Untitled"
_CATEGORY_BY_TITLE: Final[dict[str, str]] = {
    "Definitions": "Legal",
    "Payment Terms": "Commercial",
    "Termination": "Legal",
    "Premises": "Property",
    "Rent": "Commercial",
    "Maintenance": "Property",
}
_LOW_CONFIDENCE: Final[float] = 0.55
_HIGH_CONFIDENCE: Final[float] = 0.92
_RECONCILED_CONFIDENCE: Final[float] = 0.81


@final
class ModelServiceSimulator:
    def __init__(self, latency_seconds: float = 0.0) -> None:
        self._latency_seconds: float = latency_seconds

    def create_http_transport(self) -> httpx.MockTransport:
        return httpx.MockTransport(self._answer)

    async def _answer(self, model_service_request: httpx.Request) -> httpx.Response:
        await asyncio.sleep(self._latency_seconds)
        request_value_by_field_name: dict[str, Any] = json.loads(model_service_request.content)
        resource_path: str = model_service_request.url.path
        if resource_path == _SECTION_DETECTIONS_PATH:
            return self._reply(self._detect_section(request_value_by_field_name["page_text"]))
        if resource_path == _SECTION_SCORES_PATH:
            return self._reply(self._category_reply(request_value_by_field_name[_TITLE_FIELD], _LOW_CONFIDENCE))
        if resource_path == _SECTION_RECONCILIATIONS_PATH:
            return self._reply(self._category_reply(request_value_by_field_name[_TITLE_FIELD], _RECONCILED_CONFIDENCE))
        return httpx.Response(_HTTP_STATUS_NOT_FOUND, text=f"No such resource: {resource_path}")

    @classmethod
    def _detect_section(cls, page_text: str) -> str:
        title: str = cls._title_from_page(page_text)
        if MALFORMED_REPLY_MARKER in page_text:
            return f'Sure! Here is the JSON you asked for: {{"{_TITLE_FIELD}": "{title}", "{_CATEGORY_FIELD}": '
        return json.dumps({_TITLE_FIELD: title})

    @staticmethod
    def _title_from_page(page_text: str) -> str:
        lines_after_label: list[str] = page_text.partition(":")[2].splitlines()
        return lines_after_label[0].strip() if lines_after_label else _UNTITLED_PAGE_TITLE

    @staticmethod
    def _category_reply(title: str, ambiguous_title_confidence: float) -> str:
        confidence: float = ambiguous_title_confidence if title in _AMBIGUOUS_TITLES else _HIGH_CONFIDENCE
        return json.dumps({_CATEGORY_FIELD: _CATEGORY_BY_TITLE.get(title, _DEFAULT_CATEGORY), _CONFIDENCE_FIELD: confidence})

    @staticmethod
    def _reply(model_reply: str) -> httpx.Response:
        return httpx.Response(_HTTP_STATUS_OK, json={"reply": model_reply})
