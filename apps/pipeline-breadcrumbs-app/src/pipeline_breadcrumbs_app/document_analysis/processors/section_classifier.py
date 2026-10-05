"""Step 3: classify the detected sections. A sub-orchestrator.

It owns no model calls and no prompt text. It opens step 3, hands that step's scope to three
processors as their host, and decides whether the last one runs. Because it passes the step
scope down, their steps report as 3.1, 3.2 and 3.3 with no numbering code here.
"""

from pipeline_breadcrumbs import StepHostProtocol
from pipeline_breadcrumbs_app.document_analysis.analysis_steps import CLASSIFY_SECTIONS, RECONCILE_SCORES
from pipeline_breadcrumbs_app.document_analysis.models import ClassificationPrompt, DetectedSection, ScoredSection
from pipeline_breadcrumbs_app.document_analysis.processors.classification.prompt_builder import PromptBuilder
from pipeline_breadcrumbs_app.document_analysis.processors.classification.score_reconciler import ScoreReconciler
from pipeline_breadcrumbs_app.document_analysis.processors.classification.section_scorer import SectionScorer


class SectionClassifier:
    def __init__(self, prompt_builder: PromptBuilder, section_scorer: SectionScorer, score_reconciler: ScoreReconciler) -> None:
        self._prompt_builder: PromptBuilder = prompt_builder
        self._section_scorer: SectionScorer = section_scorer
        self._score_reconciler: ScoreReconciler = score_reconciler

    async def classify(self, step_host: StepHostProtocol, detected_sections: list[DetectedSection]) -> list[ScoredSection]:
        async with step_host.step(CLASSIFY_SECTIONS) as step_scope:
            classification_prompts: list[ClassificationPrompt] = await self._prompt_builder.build(step_scope, detected_sections)
            scored_sections: list[ScoredSection] = await self._section_scorer.score(step_scope, classification_prompts)
            if any(scored_section.needs_reconciliation for scored_section in scored_sections):
                classified_sections: list[ScoredSection] = await self._score_reconciler.reconcile(step_scope, scored_sections)
            else:
                # A conditional step. Its absence from the artifact folder says the same thing as this line.
                step_scope.skipped(RECONCILE_SCORES, "no sections below the confidence threshold")
                classified_sections = scored_sections
            step_scope.outcome(f"Classified {len(classified_sections)} section(s)", sections=len(classified_sections))
        return classified_sections
