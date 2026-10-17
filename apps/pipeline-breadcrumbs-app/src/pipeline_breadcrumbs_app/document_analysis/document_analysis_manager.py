"""The system's entry point.

`DocumentAnalysisManager` is what an application calls. Its one public method refuses a document
it cannot analyze, then sequences the processors and passes each one's result to the next. It does
no work of its own: every step is a processor's, and each processor opens its own step on the host
it is given.

The caller hands in the host (a work item scope). The scope carries the artifact sink and
the logger the application chose, so the manager and everything below it know neither where
artifacts land nor how the log is written. The service locator supplies the rest of what a host
may swap: the configuration source and the HTTP transport under the model service gateway.
"""

from types import TracebackType
from typing import Self

from pipeline_breadcrumbs import StepHostProtocol
from pipeline_breadcrumbs_app.document_analysis.configuration_providers.configuration_provider import ConfigurationProvider
from pipeline_breadcrumbs_app.document_analysis.configuration_providers.settings_models.model_service_settings import ModelServiceSettings
from pipeline_breadcrumbs_app.document_analysis.configuration_providers.settings_models.simulated_work_settings import SimulatedWorkSettings
from pipeline_breadcrumbs_app.document_analysis.engines.section_classifier import SectionClassifier
from pipeline_breadcrumbs_app.document_analysis.gateways.gateway_model_service import GatewayModelService
from pipeline_breadcrumbs_app.document_analysis.models import DetectedSection, DocumentAnalysis, ScoredSection
from pipeline_breadcrumbs_app.document_analysis.processors.page_loader import PageLoader
from pipeline_breadcrumbs_app.document_analysis.processors.report_assembler import ReportAssembler
from pipeline_breadcrumbs_app.document_analysis.processors.section_detector import SectionDetector
from pipeline_breadcrumbs_app.document_analysis.service_locators.service_locator_base import ServiceLocatorBase
from pipeline_breadcrumbs_app.document_analysis.validators.document_analysis_validator import DocumentAnalysisValidator


class DocumentAnalysisManager:
    """Owns the model service gateway for its lifetime. Use `async with`, or call `close()`; both are safe."""

    def __init__(self, service_locator: ServiceLocatorBase) -> None:
        # Configuration is read before anything that owns a resource is built: a configuration failure part way
        # through would otherwise leave a constructed gateway that nothing ever closes.
        configuration_provider: ConfigurationProvider = service_locator.get_configuration_provider()
        model_service_settings: ModelServiceSettings = configuration_provider.get_model_service_settings()
        simulated_work_settings: SimulatedWorkSettings = configuration_provider.get_simulated_work_settings()

        self._gateway_model_service: GatewayModelService = GatewayModelService(
            model_service_settings.base_url, service_locator.create_http_transport()
        )
        self._page_loader: PageLoader = PageLoader(simulated_work_settings.delay_seconds)
        self._section_detector: SectionDetector = SectionDetector(self._gateway_model_service)
        self._section_classifier: SectionClassifier = SectionClassifier(self._gateway_model_service, simulated_work_settings.delay_seconds)
        self._report_assembler: ReportAssembler = ReportAssembler(simulated_work_settings.delay_seconds)
        self._closed: bool = False

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, _exc_type: type[BaseException] | None, _exc: BaseException | None, _traceback: TracebackType | None) -> None:
        await self.close()

    async def close(self) -> None:
        if self._closed:
            return
        await self._gateway_model_service.close()
        self._closed = True

    async def analyze_document(self, step_host: StepHostProtocol, pages: list[str]) -> DocumentAnalysis:
        DocumentAnalysisValidator.validate(pages)
        loaded_pages: list[str] = await self._page_loader.load(step_host, pages)
        detected_sections: list[DetectedSection] = await self._section_detector.detect(step_host, loaded_pages)
        classified_scored_sections: list[ScoredSection] = await self._section_classifier.classify(step_host, detected_sections)
        report: str = await self._report_assembler.assemble(step_host, classified_scored_sections)
        return DocumentAnalysis(scored_sections=classified_scored_sections, report=report)
