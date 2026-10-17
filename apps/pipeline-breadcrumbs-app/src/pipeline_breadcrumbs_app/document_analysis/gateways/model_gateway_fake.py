"""A deterministic stand-in for the model, so the demo runs offline and reads the same every time.

Every call sleeps for `latency_seconds`, the way a real call takes time, so the log appears at a
believable pace. No network, no API key, no configuration.
"""

import asyncio
import json
from typing import Final

from pipeline_breadcrumbs_app.document_analysis.models import ClassificationPrompt

# A page containing this marker gets a chatty, non-JSON reply, to show how a failure looks.
# The fault travels in the input, so the gateway needs to know nothing about which document it serves.
MALFORMED_REPLY_MARKER: Final[str] = "[[demo: the model replies with malformed JSON for this page]]"

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
_TITLE_FIELD: Final[str] = "title"
_CATEGORY_FIELD: Final[str] = "category"
_CONFIDENCE_FIELD: Final[str] = "confidence"


class ModelGatewayFake:
    def __init__(self, latency_seconds: float = 0.0) -> None:
        self._latency_seconds: float = latency_seconds

    async def detect_section(self, page_number: int, page_text: str) -> str:  # noqa: ARG002 - the real gateway receives the page number too
        await asyncio.sleep(self._latency_seconds)
        title: str = self._title_from_page(page_text)
        if MALFORMED_REPLY_MARKER in page_text:
            return f'Sure! Here is the JSON you asked for: {{"{_TITLE_FIELD}": "{title}", "{_CATEGORY_FIELD}": '
        return json.dumps({_TITLE_FIELD: title})

    async def score_section(self, classification_prompt: ClassificationPrompt) -> str:
        await asyncio.sleep(self._latency_seconds)
        confidence: float = _LOW_CONFIDENCE if self._is_ambiguous(classification_prompt.title) else _HIGH_CONFIDENCE
        return self._category_reply(classification_prompt.title, confidence)

    async def reconcile_section(self, classification_prompt: ClassificationPrompt) -> str:
        await asyncio.sleep(self._latency_seconds)
        confidence: float = _RECONCILED_CONFIDENCE if self._is_ambiguous(classification_prompt.title) else _HIGH_CONFIDENCE
        return self._category_reply(classification_prompt.title, confidence)

    @staticmethod
    def _title_from_page(page_text: str) -> str:
        lines_after_label: list[str] = page_text.partition(":")[2].splitlines()
        return lines_after_label[0].strip() if lines_after_label else _UNTITLED_PAGE_TITLE

    @staticmethod
    def _is_ambiguous(title: str) -> bool:
        return title in _AMBIGUOUS_TITLES

    @staticmethod
    def _category_reply(title: str, confidence: float) -> str:
        return json.dumps({_CATEGORY_FIELD: _CATEGORY_BY_TITLE.get(title, _DEFAULT_CATEGORY), _CONFIDENCE_FIELD: confidence})
