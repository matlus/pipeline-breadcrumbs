import asyncio
import json
from collections.abc import Mapping

from pipeline_breadcrumbs_app.document_analysis.models import ClassificationPrompt


class ModelGatewayTesting:
    """A scripted model: it answers each question with the reply the scenario arranged, and keeps count of what it was asked.

    It replaces only the model, the one collaborator that is slow, costly and nondeterministic in
    production. Everything else in the system runs for real.
    """

    def __init__(
        self,
        detection_reply_by_page_number: Mapping[int, str],
        score_reply_by_title: Mapping[str, str],
        reconcile_reply_by_title: Mapping[str, str] | None = None,
    ) -> None:
        self._detection_reply_by_page_number: Mapping[int, str] = detection_reply_by_page_number
        self._score_reply_by_title: Mapping[str, str] = score_reply_by_title
        self._reconcile_reply_by_title: Mapping[str, str] = reconcile_reply_by_title or {}
        self._concurrent_detection_count: int = 0
        self.asked_detection_page_numbers: list[int] = []
        self.asked_score_titles: list[str] = []
        self.asked_reconcile_titles: list[str] = []
        self.maximum_concurrent_detection_count: int = 0

    async def detect_section(self, page_number: int, page_text: str) -> str:
        self.asked_detection_page_numbers.append(page_number)
        self._concurrent_detection_count += 1
        self.maximum_concurrent_detection_count = max(self.maximum_concurrent_detection_count, self._concurrent_detection_count)
        try:
            await asyncio.sleep(0)
            return self._detection_reply_by_page_number[page_number]
        finally:
            self._concurrent_detection_count -= 1

    async def score_section(self, classification_prompt: ClassificationPrompt) -> str:
        self.asked_score_titles.append(classification_prompt.title)
        return self._score_reply_by_title[classification_prompt.title]

    async def reconcile_section(self, classification_prompt: ClassificationPrompt) -> str:
        self.asked_reconcile_titles.append(classification_prompt.title)
        return self._reconcile_reply_by_title[classification_prompt.title]

    def total_question_count(self) -> int:
        return len(self.asked_detection_page_numbers) + len(self.asked_score_titles) + len(self.asked_reconcile_titles)


def create_title_reply(title: str) -> str:
    return json.dumps({"title": title})


def create_score_reply(category: str, confidence: float) -> str:
    return json.dumps({"category": category, "confidence": confidence})
