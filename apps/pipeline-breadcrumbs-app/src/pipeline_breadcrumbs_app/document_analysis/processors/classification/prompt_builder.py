"""Step 3.1: build the classification prompts. A non-model processor."""

from pipeline_breadcrumbs import StepHostProtocol
from pipeline_breadcrumbs_app.document_analysis.analysis_steps import PREPARE_PROMPTS
from pipeline_breadcrumbs_app.document_analysis.artifact_kinds import CLASSIFICATION_PROMPTS
from pipeline_breadcrumbs_app.document_analysis.json_documents import to_json_document
from pipeline_breadcrumbs_app.document_analysis.models import ClassificationPrompt, DetectedSection
from pipeline_breadcrumbs_app.document_analysis.simulated_work import SimulatedWork


class PromptBuilder:
    def __init__(self, simulated_work: SimulatedWork) -> None:
        self._simulated_work: SimulatedWork = simulated_work

    async def build(self, step_host: StepHostProtocol, detected_sections: list[DetectedSection]) -> list[ClassificationPrompt]:
        async with step_host.step(PREPARE_PROMPTS) as step_scope:
            step_scope.info("Preparing prompts", sections=len(detected_sections))
            classification_prompts: list[ClassificationPrompt] = await self._compose_prompts(detected_sections)
            await step_scope.emit(CLASSIFICATION_PROMPTS, to_json_document(classification_prompts))
            step_scope.outcome(f"Prepared {len(classification_prompts)} prompt(s)", prompts=len(classification_prompts))
        return classification_prompts

    async def _compose_prompts(self, detected_sections: list[DetectedSection]) -> list[ClassificationPrompt]:
        classification_prompts: list[ClassificationPrompt] = []
        for detected_section in detected_sections:
            # A real processor merges the section's text into a prompt template loaded from a prompt file.
            await self._simulated_work.take_time()
            prompt_text: str = f"Classify the section titled '{detected_section.title}' on page {detected_section.page_number} into one category."
            classification_prompts.append(ClassificationPrompt(detected_section.page_number, detected_section.title, prompt_text))
        return classification_prompts
