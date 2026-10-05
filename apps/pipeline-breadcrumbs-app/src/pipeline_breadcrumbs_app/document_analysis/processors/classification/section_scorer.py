"""Step 3.2: ask the model to categorise each section and say how sure it is. A model processor."""

from collections.abc import Iterable

from pipeline_breadcrumbs import StepHostProtocol, StepScope
from pipeline_breadcrumbs_app.document_analysis.analysis_steps import SCORE_SECTIONS
from pipeline_breadcrumbs_app.document_analysis.artifact_kinds import RAW_SCORE_RESPONSE, SECTION_SCORES, page_discriminator
from pipeline_breadcrumbs_app.document_analysis.gateways.model_gateway import ModelGatewayProtocol
from pipeline_breadcrumbs_app.document_analysis.json_documents import to_json_document
from pipeline_breadcrumbs_app.document_analysis.model_reply import ModelReply
from pipeline_breadcrumbs_app.document_analysis.models import ClassificationPrompt, ScoredSection


class SectionScorer:
    def __init__(self, model_gateway: ModelGatewayProtocol) -> None:
        self._model_gateway: ModelGatewayProtocol = model_gateway

    async def score(self, step_host: StepHostProtocol, classification_prompts: list[ClassificationPrompt]) -> list[ScoredSection]:
        async with step_host.step(SCORE_SECTIONS) as step_scope:
            step_scope.info("Scoring sections", sections=len(classification_prompts))
            scored_sections: list[ScoredSection] = await self._score_each(step_scope, classification_prompts)
            await step_scope.emit(SECTION_SCORES, to_json_document(scored_sections))
            self._report_outcome(step_scope, scored_sections)
        return scored_sections

    async def _score_each(self, step_scope: StepScope, classification_prompts: Iterable[ClassificationPrompt]) -> list[ScoredSection]:
        scored_sections: list[ScoredSection] = []
        for classification_prompt in classification_prompts:
            step_scope.info("Calling the model", page=classification_prompt.page_number, title=classification_prompt.title)
            # A real gateway merges the prompt into a prompt template before it sends it to the model.
            raw_reply: str = await self._model_gateway.score_section(classification_prompt)
            await step_scope.emit(RAW_SCORE_RESPONSE, raw_reply.encode("utf-8"), discriminator=page_discriminator(classification_prompt.page_number))
            scored_sections.append(self._parse(classification_prompt, raw_reply))
        return scored_sections

    @staticmethod
    def _report_outcome(step_scope: StepScope, scored_sections: list[ScoredSection]) -> None:
        doubtful_count: int = sum(1 for scored_section in scored_sections if scored_section.needs_reconciliation)
        step_scope.outcome(f"Scored {len(scored_sections)} section(s); {doubtful_count} below the confidence threshold", doubtful=doubtful_count)

    @staticmethod
    def _parse(classification_prompt: ClassificationPrompt, raw_reply: str) -> ScoredSection:
        model_reply: ModelReply = ModelReply.parse(classification_prompt.page_number, raw_reply)
        return ScoredSection(
            page_number=classification_prompt.page_number,
            title=classification_prompt.title,
            category=model_reply.require_text("category"),
            confidence=model_reply.require_confidence(),
        )
