"""Step 2: detect the section each page starts. A model processor that fans out across pages."""

import asyncio
from typing import Final

from pipeline_breadcrumbs import StepHostProtocol, StepScope
from pipeline_breadcrumbs_app.document_analysis.analysis_steps import DETECT_SECTIONS
from pipeline_breadcrumbs_app.document_analysis.artifact_kinds import DETECTED_SECTIONS, RAW_DETECTION_RESPONSE, page_discriminator
from pipeline_breadcrumbs_app.document_analysis.gateways.model_gateway import ModelGatewayProtocol
from pipeline_breadcrumbs_app.document_analysis.json_documents import to_json_document
from pipeline_breadcrumbs_app.document_analysis.model_reply import ModelReply
from pipeline_breadcrumbs_app.document_analysis.models import DetectedSection

MAX_CONCURRENCY: Final[int] = 3


class SectionDetector:
    def __init__(self, model_gateway: ModelGatewayProtocol) -> None:
        self._model_gateway: ModelGatewayProtocol = model_gateway

    async def detect(self, step_host: StepHostProtocol, pages: list[str]) -> list[DetectedSection]:
        async with step_host.step(DETECT_SECTIONS) as step_scope:
            step_scope.info("Detecting sections", pages=len(pages), concurrency=MAX_CONCURRENCY)
            page_outcomes: list[DetectedSection | BaseException] = await self._detect_all_pages(step_scope, pages)
            detected_sections: list[DetectedSection] = self._sections_or_first_failure(page_outcomes)
            await step_scope.emit(DETECTED_SECTIONS, to_json_document(detected_sections))
            step_scope.outcome(f"Detected {len(detected_sections)} section(s)", sections=len(detected_sections))
        return detected_sections

    async def _detect_all_pages(self, step_scope: StepScope, pages: list[str]) -> list[DetectedSection | BaseException]:
        page_semaphore: asyncio.Semaphore = asyncio.Semaphore(MAX_CONCURRENCY)
        return await asyncio.gather(
            *(self._detect_page(step_scope, page_semaphore, page_number, pages[page_number]) for page_number in range(len(pages))),
            return_exceptions=True,
        )

    async def _detect_page(self, step_scope: StepScope, page_semaphore: asyncio.Semaphore, page_number: int, page_text: str) -> DetectedSection:
        async with page_semaphore:
            step_scope.info("Calling the model", page=page_number)
            # A real processor sends the page and its prompt to the model here.
            raw_reply: str = await self._model_gateway.detect_section(page_number, page_text)
            # Emit before validating: if parsing fails, the raw reply is already on disk.
            await step_scope.emit(RAW_DETECTION_RESPONSE, raw_reply.encode("utf-8"), discriminator=page_discriminator(page_number))
            detected_section: DetectedSection = self._parse(page_number, raw_reply)
            step_scope.info("Detected a section", page=page_number, title=detected_section.title)
            return detected_section

    @staticmethod
    def _sections_or_first_failure(page_outcomes: list[DetectedSection | BaseException]) -> list[DetectedSection]:
        # Every page ran, so every raw reply is on disk; then the first failure, in page order, ends the step.
        detected_sections: list[DetectedSection] = []
        for page_outcome in page_outcomes:
            if isinstance(page_outcome, BaseException):
                raise page_outcome
            detected_sections.append(page_outcome)
        return detected_sections

    @staticmethod
    def _parse(page_number: int, raw_reply: str) -> DetectedSection:
        model_reply: ModelReply = ModelReply.parse(page_number, raw_reply)
        return DetectedSection(page_number, model_reply.require_text("title"))
