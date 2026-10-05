"""Step 3.3: ask the model again about the sections it was unsure of. A conditional model processor."""

from pipeline_breadcrumbs import StepHostProtocol, StepScope
from pipeline_breadcrumbs_app.document_analysis.analysis_steps import RECONCILE_SCORES
from pipeline_breadcrumbs_app.document_analysis.artifact_kinds import RAW_RECONCILIATION_RESPONSE, RECONCILED_SCORES, page_discriminator
from pipeline_breadcrumbs_app.document_analysis.gateways.model_gateway import ModelGatewayProtocol
from pipeline_breadcrumbs_app.document_analysis.json_documents import to_json_document
from pipeline_breadcrumbs_app.document_analysis.model_reply import ModelReply
from pipeline_breadcrumbs_app.document_analysis.models import ClassificationPrompt, ScoredSection


class ScoreReconciler:
    def __init__(self, model_gateway: ModelGatewayProtocol) -> None:
        self._model_gateway: ModelGatewayProtocol = model_gateway

    async def reconcile(self, step_host: StepHostProtocol, scored_sections: list[ScoredSection]) -> list[ScoredSection]:
        async with step_host.step(RECONCILE_SCORES) as step_scope:
            doubtful_count: int = sum(1 for scored_section in scored_sections if scored_section.needs_reconciliation)
            step_scope.info("Reconciling low-confidence sections", sections=doubtful_count)
            reconciled_sections: list[ScoredSection] = await self._reconcile_each(step_scope, scored_sections)
            await step_scope.emit(RECONCILED_SCORES, to_json_document(reconciled_sections))
            step_scope.outcome(f"Reconciled {doubtful_count} section(s)", reconciled=doubtful_count)
        return reconciled_sections

    async def _reconcile_each(self, step_scope: StepScope, scored_sections: list[ScoredSection]) -> list[ScoredSection]:
        reconciled_sections: list[ScoredSection] = []
        for initial_scored_section in scored_sections:
            if initial_scored_section.needs_reconciliation:
                reconciled_sections.append(await self._reconcile_section(step_scope, initial_scored_section))
            else:
                reconciled_sections.append(initial_scored_section)
        return reconciled_sections

    async def _reconcile_section(self, step_scope: StepScope, initial_scored_section: ScoredSection) -> ScoredSection:
        step_scope.info(
            "Calling the model again",
            page=initial_scored_section.page_number,
            title=initial_scored_section.title,
            was=initial_scored_section.confidence,
        )
        # A real processor asks the model a sharper follow-up question here.
        classification_prompt: ClassificationPrompt = ClassificationPrompt(
            initial_scored_section.page_number, initial_scored_section.title, f"Reconsider the section titled '{initial_scored_section.title}'."
        )
        raw_reply: str = await self._model_gateway.reconcile_section(classification_prompt)
        await step_scope.emit(
            RAW_RECONCILIATION_RESPONSE, raw_reply.encode("utf-8"), discriminator=page_discriminator(initial_scored_section.page_number)
        )
        reconciled_scored_section: ScoredSection = self._parse(initial_scored_section, raw_reply)
        step_scope.info(
            "Reconciled a section",
            page=initial_scored_section.page_number,
            title=initial_scored_section.title,
            now=reconciled_scored_section.confidence,
        )
        return reconciled_scored_section

    @staticmethod
    def _parse(scored_section: ScoredSection, raw_reply: str) -> ScoredSection:
        model_reply: ModelReply = ModelReply.parse(scored_section.page_number, raw_reply)
        return ScoredSection(
            page_number=scored_section.page_number,
            title=scored_section.title,
            category=model_reply.require_text("category"),
            confidence=model_reply.require_confidence(),
        )
