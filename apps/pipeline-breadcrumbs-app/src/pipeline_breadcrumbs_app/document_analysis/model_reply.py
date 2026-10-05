"""Turning an untrusted model reply into checked values.

A model reply is input from outside the system. Syntactically valid JSON of the wrong shape
(a list, `null`, a title that is not text, a confidence of "high" or `NaN`) is as unusable as
malformed JSON, so every case ends the same way: a `ModelResponseParseError` carrying the page.
"""

import json
from collections.abc import Mapping
from typing import Any, cast, final

from pipeline_breadcrumbs_app.document_analysis.exceptions import ModelResponseParseError


def _describe_rejected_value(rejected_value: object) -> str:
    """A bounded, safe description: the number itself, or just the type, never an arbitrary payload."""
    if rejected_value is None:
        return "nothing (the field is missing)"
    if isinstance(rejected_value, bool):
        return "a boolean"
    if isinstance(rejected_value, int | float):
        return f"the number {rejected_value!r}"
    if isinstance(rejected_value, str):
        return "blank text" if not rejected_value.strip() else "text"
    return f"a value of type {type(rejected_value).__name__}"


@final
class ModelReply:
    """A model reply that parsed as a JSON object. It keeps its fields private and answers for them."""

    def __init__(self, page_number: int, reply_value_by_field_name: Mapping[str, Any]) -> None:
        self._page_number: int = page_number
        self._reply_value_by_field_name: Mapping[str, Any] = dict(reply_value_by_field_name)

    @staticmethod
    def parse(page_number: int, raw_reply: str) -> ModelReply:
        try:
            parsed_reply: Any = json.loads(raw_reply)
        except (ValueError, RecursionError) as error:
            # JSONDecodeError is a ValueError. So is the error for an absurdly long digit string, and a deeply
            # nested reply raises RecursionError; to the system all three are the same unusable reply.
            raise ModelResponseParseError(page_number, f"{type(error).__name__}: {error}") from error
        if not isinstance(parsed_reply, dict):
            raise ModelResponseParseError(page_number, f"expected a JSON object, got {type(parsed_reply).__name__}")
        return ModelReply(page_number, cast("dict[str, Any]", parsed_reply))

    def require_text(self, field_name: str) -> str:
        field_value: Any = self._reply_value_by_field_name.get(field_name)
        if not isinstance(field_value, str) or not field_value.strip():
            raise ModelResponseParseError(self._page_number, f"'{field_name}' must be non-empty text, got {_describe_rejected_value(field_value)}")
        return field_value.strip()

    def require_confidence(self, field_name: str = "confidence") -> float:
        field_value: Any = self._reply_value_by_field_name.get(field_name)
        if isinstance(field_value, bool) or not isinstance(field_value, int | float) or not 0.0 <= field_value <= 1.0:
            raise ModelResponseParseError(
                self._page_number, f"'{field_name}' must be a number from 0 to 1, got {_describe_rejected_value(field_value)}"
            )
        return float(field_value)
