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


class FakeModelGateway:
    def __init__(self, latency_seconds: float = 0.0) -> None:
        self._latency_seconds: float = latency_seconds

    async def detect_section(self, page_number: int, page_text: str) -> str:  # noqa: ARG002 - the real gateway receives the page number too
        await asyncio.sleep(self._latency_seconds)
        text_after_label: list[str] = page_text.partition(":")[2].splitlines()
        title: str = text_after_label[0].strip() if text_after_label else _UNTITLED_PAGE_TITLE
        if MALFORMED_REPLY_MARKER in page_text:
            return f'Sure! Here is the JSON you asked for: {{"title": "{title}", "category": '
        return json.dumps({"title": title})

    async def score_section(self, classification_prompt: ClassificationPrompt) -> str:
        await asyncio.sleep(self._latency_seconds)
        confidence: float = _LOW_CONFIDENCE if classification_prompt.title in _AMBIGUOUS_TITLES else _HIGH_CONFIDENCE
        return json.dumps({"category": _CATEGORY_BY_TITLE.get(classification_prompt.title, _DEFAULT_CATEGORY), "confidence": confidence})

    async def reconcile_section(self, classification_prompt: ClassificationPrompt) -> str:
        await asyncio.sleep(self._latency_seconds)
        confidence: float = _RECONCILED_CONFIDENCE if classification_prompt.title in _AMBIGUOUS_TITLES else _HIGH_CONFIDENCE
        return json.dumps({"category": _CATEGORY_BY_TITLE.get(classification_prompt.title, _DEFAULT_CATEGORY), "confidence": confidence})
