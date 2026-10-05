"""The system's entry point.

`DocumentAnalysisManager` is what an application calls. Its one public method refuses a document
it cannot analyze, then sequences the processors and passes each one's result to the next. It does
no work of its own: every step is a processor's, and each processor opens its own step on the host
it is given.

The caller hands in the host (a work item scope). The scope carries the artifact callback and
the logger the application chose, so the manager and everything below it know neither where
artifacts land nor how the log is written.
"""

from pipeline_breadcrumbs import StepHostProtocol
from pipeline_breadcrumbs_app.document_analysis.gateways.model_gateway import ModelGatewayProtocol
from pipeline_breadcrumbs_app.document_analysis.models import DetectedSection, DocumentAnalysis, ScoredSection
from pipeline_breadcrumbs_app.document_analysis.processors.classification.prompt_builder import PromptBuilder
from pipeline_breadcrumbs_app.document_analysis.processors.classification.score_reconciler import ScoreReconciler
from pipeline_breadcrumbs_app.document_analysis.processors.classification.section_scorer import SectionScorer
from pipeline_breadcrumbs_app.document_analysis.processors.page_loader import PageLoader
from pipeline_breadcrumbs_app.document_analysis.processors.report_assembler import ReportAssembler
from pipeline_breadcrumbs_app.document_analysis.processors.section_classifier import SectionClassifier
from pipeline_breadcrumbs_app.document_analysis.processors.section_detector import SectionDetector
from pipeline_breadcrumbs_app.document_analysis.simulated_work import SimulatedWork
from pipeline_breadcrumbs_app.document_analysis.validators.document_analysis_validator import DocumentAnalysisValidator


class DocumentAnalysisManager:
    def __init__(self, model_gateway: ModelGatewayProtocol, simulated_work: SimulatedWork) -> None:
        self._page_loader: PageLoader = PageLoader(simulated_work)
        self._section_detector: SectionDetector = SectionDetector(model_gateway)
        self._section_classifier: SectionClassifier = SectionClassifier(
            PromptBuilder(simulated_work),
            SectionScorer(model_gateway),
            ScoreReconciler(model_gateway),
        )
        self._report_assembler: ReportAssembler = ReportAssembler(simulated_work)

    async def analyze_document(self, step_host: StepHostProtocol, pages: list[str]) -> DocumentAnalysis:
        DocumentAnalysisValidator.validate(pages)
        loaded_pages: list[str] = await self._page_loader.load(step_host, pages)
        detected_sections: list[DetectedSection] = await self._section_detector.detect(step_host, loaded_pages)
        classified_sections: list[ScoredSection] = await self._section_classifier.classify(step_host, detected_sections)
        report: str = await self._report_assembler.assemble(step_host, classified_sections)
        return DocumentAnalysis(sections=classified_sections, report=report)
