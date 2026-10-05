"""Builds the system under test the way an application builds it, with only the model replaced."""

import logging

from analysis_acceptance_support.model_gateway_testing import ModelGatewayTesting
from pipeline_breadcrumbs import PipelineRun, WorkItem
from pipeline_breadcrumbs.testing import ArtifactRecorder
from pipeline_breadcrumbs_app.document_analysis.document_analysis_manager import DocumentAnalysisManager
from pipeline_breadcrumbs_app.document_analysis.models import DocumentAnalysis
from pipeline_breadcrumbs_app.document_analysis.simulated_work import SimulatedWork


def create_document_analysis_manager(model_gateway_testing: ModelGatewayTesting) -> DocumentAnalysisManager:
    return DocumentAnalysisManager(model_gateway_testing, SimulatedWork(0.0))


async def analyze_in_a_run(
    document_analysis_manager: DocumentAnalysisManager,
    pages: list[str],
    work_item: WorkItem,
    artifact_recorder: ArtifactRecorder,
    run_logger: logging.Logger,
) -> DocumentAnalysis:
    """What an application does: open a run and a work item, hand the work item's scope to the system, close the run."""
    async with (
        PipelineRun(name="document-analysis-test", sink=artifact_recorder, logger=run_logger) as pipeline_run,
        pipeline_run.work_item(work_item) as work_item_scope,
    ):
        return await document_analysis_manager.analyze_document(work_item_scope, pages)
