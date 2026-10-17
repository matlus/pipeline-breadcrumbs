"""The demo application: the thing that calls the system. It is not part of the system.

The system is `DocumentAnalysisManager`. This module is the application around it, and it makes
every decision the system must not make:

* where artifacts go: it chooses the artifact sink, a class that implements `ArtifactSinkProtocol`. A
  local run hands in the file-system sink and a hosted run hands in the blob-storage one. Every artifact
  is persisted either way, because artifacts are the record of what each step did;
* where log lines go: it builds the one logger the system shares and decides which handlers listen
  to it. Those handlers and the artifact sink are the only things a local run and a hosted run do differently;
* which model service the system talks to: it hands the system `ServiceLocatorDemo`, whose transport
  answers the model service's API in-process, so the demo runs offline with the system's real gateway;
* what to run and what to do when it fails: it opens the run, opens one work item per document,
  calls the system, and logs a failure once, at this outer boundary. That includes a run whose
  manifest cannot be persisted when it closes; the run is then reported as failed.

The system receives the sink and the logger through the scope it is handed, and never sees a path, a
container or a handler.

    uv run pipeline_breadcrumbs_app                     # local: console, a run log beside the artifacts
    uv run pipeline_breadcrumbs_app --host hosted       # hosted: console, and exceptions only to telemetry
    uv run pipeline_breadcrumbs_app --fail-page 2       # Contract 12 gets a malformed model reply on page 2
"""

import argparse
import asyncio
import logging
import sys
from collections.abc import Generator, Mapping
from contextlib import ExitStack, contextmanager
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Final
from uuid import uuid4

from pipeline_breadcrumbs import (
    ArtifactSinkError,
    ArtifactSinkProtocol,
    AttributeKey,
    BreadcrumbFormatter,
    Clock,
    ContextualExceptionProtocol,
    PipelineRun,
    StepStatus,
    TimeDisplay,
    WorkItem,
    WorkItemScope,
)
from pipeline_breadcrumbs.hosting import ArtifactSinkFileSystem, attached_run_log, create_run_folder
from pipeline_breadcrumbs_app.artifact_sink_blob_storage import ArtifactSinkBlobStorage
from pipeline_breadcrumbs_app.document_analysis.document_analysis_manager import DocumentAnalysisManager
from pipeline_breadcrumbs_app.document_analysis.exceptions import DocumentAnalysisBusinessError, DocumentAnalysisTechnicalError
from pipeline_breadcrumbs_app.sample_documents import SAMPLE_DOCUMENTS, InvalidFailPageError, with_malformed_reply
from pipeline_breadcrumbs_app.service_locator_demo import ServiceLocatorDemo
from pipeline_breadcrumbs_app.telemetry import TELEMETRY_FILENAME, attached_exception_telemetry

PIPELINE_NAME: Final[str] = "document-analysis-demo"
BLOB_CONTAINER_NAME: Final[str] = "artifact-container"
LOGGER_NAME: Final[str] = "pipeline_breadcrumbs_app"

# How long a simulated model call takes. Other simulated work takes a third of it. The delay is
# there so a person watching sees the flow go from step to step; fifteen lines arriving in one
# second explain nothing. It is not a command-line switch, because a teaching sample should need
# no switches to read well. Tests pass 0 to `run_demo` and run instantly.
DEFAULT_PACE_SECONDS: Final[float] = 0.3


class HostProfile(StrEnum):
    """Where the application runs. The system behaves the same in both; only the log handlers and the artifact sink differ.

    Local keeps every informational line in a `run.log` beside the artifacts, for a developer who is
    watching the run, and writes the artifacts to the file system. Hosted leaves informational lines to the
    platform's own process logs (the console here), sends only exceptions to telemetry, the way an Azure ML
    pipeline reports to Application Insights, and uploads the artifacts to blob storage.
    """

    LOCAL = "local"
    HOSTED = "hosted"


@dataclass(frozen=True, slots=True)
class DemoRunRequest:
    """One demo run: where its folders go, how it reads, where it pretends to be hosted, and how fast it goes.

    `fail_page` gives Contract 12 a malformed model reply on that zero-based page. `pace_seconds` is how
    long a simulated model call takes; other simulated work takes a third of that. The default makes the log
    readable as it appears; a test passes 0 to run instantly. `supplied_clock` names the run folder and
    times the run. Left out, the system clock does; a test supplies a fixed one when it must know the run
    folder's name before the run starts.
    """

    output_root: Path
    fail_page: int | None = None
    time_display: TimeDisplay = TimeDisplay.BOUNDARIES
    host_profile: HostProfile = HostProfile.LOCAL
    pace_seconds: float = DEFAULT_PACE_SECONDS
    supplied_clock: Clock | None = None


@dataclass(frozen=True, slots=True)
class DemoResult:
    """Where the trail landed: the run's own folder, the place its artifacts went, how the run ended, and which documents failed.

    A local run keeps its artifacts in its run folder, so the two are the same. A hosted run keeps only its
    telemetry there and uploads its artifacts to the blob container. A run fails when a document fails, and
    also when its manifest cannot be persisted, even if every document succeeded.
    """

    run_directory: Path
    artifact_directory: Path
    run_status: StepStatus
    failed_work_items: list[str]


@dataclass(frozen=True, slots=True)
class AnalysisOutcome:
    run_status: StepStatus
    failed_work_items: list[str]


@dataclass(frozen=True, slots=True)
class ArtifactDestination:
    artifact_sink: ArtifactSinkProtocol
    artifact_directory: Path


def _create_file_system_destination(run_directory: Path) -> ArtifactDestination:
    return ArtifactDestination(ArtifactSinkFileSystem(run_directory), run_directory)


def _create_blob_storage_destination(output_root: Path, run_directory: Path) -> ArtifactDestination:
    # A container holds many runs, so each run's blobs sit under its run folder's name.
    run_blob_directory: Path = output_root / BLOB_CONTAINER_NAME / run_directory.name
    return ArtifactDestination(ArtifactSinkBlobStorage(run_blob_directory), run_blob_directory)


@contextmanager
def _console_logger(formatter: logging.Formatter) -> Generator[logging.Logger]:
    """The demo's own logger: the console, with propagation off so root handlers do not repeat each line.

    The logger itself passes every informational line; each handler decides what it wants. Everything
    this changes on the process-wide logger is put back on exit.
    """
    logger: logging.Logger = logging.getLogger(LOGGER_NAME)
    console: logging.Handler = logging.StreamHandler(sys.stdout)
    console.setFormatter(formatter)
    previous_level: int = logger.level
    previous_propagate: bool = logger.propagate
    logger.addHandler(console)
    logger.setLevel(logging.INFO)
    logger.propagate = False
    try:
        yield logger
    finally:
        logger.removeHandler(console)
        logger.setLevel(previous_level)
        logger.propagate = previous_propagate


def _describe_contextual_data(contextual_exception: ContextualExceptionProtocol) -> str:
    fact_lines: list[str] = []
    fact_name: str
    fact_value: object
    for fact_name, fact_value in contextual_exception.contextual_data_by_name.items():
        fact_lines.append(f"  {fact_name}: {fact_value}")
    return "\n".join(fact_lines)


def _identify_run(pipeline_run: PipelineRun) -> dict[str, str]:
    return {AttributeKey.PIPELINE_NAME: PIPELINE_NAME, AttributeKey.RUN_ID: pipeline_run.run_id}


def _identify_work_item(pipeline_run: PipelineRun, document_name: str) -> dict[str, str]:
    return {**_identify_run(pipeline_run), AttributeKey.WORK_ITEM_NAME: document_name}


async def _analyze_work_items(
    pipeline_run: PipelineRun,
    pages_by_document_name: Mapping[str, list[str]],
    document_analysis_manager: DocumentAnalysisManager,
    logger: logging.Logger,
) -> list[str]:
    failed_document_names: list[str] = []
    document_name: str
    pages: list[str]
    for document_name, pages in pages_by_document_name.items():
        try:
            work_item_scope: WorkItemScope
            async with pipeline_run.open_work_item(WorkItem(id=str(uuid4()), name=document_name)) as work_item_scope:
                await document_analysis_manager.analyze_document(work_item_scope, pages)
        except DocumentAnalysisBusinessError as document_analysis_business_error:
            # The document itself cannot be analyzed; whoever sent it can correct it. A warning names every problem,
            # and no traceback, because nothing in the system failed.
            logger.warning(
                "Work item '%s' was rejected:\n%s",
                document_name,
                _describe_contextual_data(document_analysis_business_error),
                extra=_identify_work_item(pipeline_run, document_name),
            )
            failed_document_names.append(document_name)
        except (DocumentAnalysisTechnicalError, ArtifactSinkError) as technical_error:
            # The application's single outer boundary for failures an operator owns: the exception is logged once,
            # with its traceback and every named fact it carries. Steps only leave breadcrumbs. The run and work
            # item identity travel as attributes, so telemetry can tell which run this was.
            logger.error(
                "Work item '%s' failed:\n%s",
                document_name,
                _describe_contextual_data(technical_error),
                exc_info=technical_error,
                extra=_identify_work_item(pipeline_run, document_name),
            )
            failed_document_names.append(document_name)
    return failed_document_names


async def _analyze_documents(
    pages_by_document_name: Mapping[str, list[str]],
    document_analysis_manager: DocumentAnalysisManager,
    artifact_sink: ArtifactSinkProtocol,
    logger: logging.Logger,
    run_clock: Clock,
) -> AnalysisOutcome:
    pipeline_run: PipelineRun = PipelineRun(pipeline_name=PIPELINE_NAME, artifact_sink=artifact_sink, logger=logger, supplied_clock=run_clock)
    failed_document_names: list[str] = []
    try:
        async with pipeline_run:
            failed_document_names = await _analyze_work_items(pipeline_run, pages_by_document_name, document_analysis_manager, logger)
    except ArtifactSinkError as artifact_sink_error:
        # Every work item's failure was handled above, so a sink failure that reaches here is the manifest the run
        # persists as it closes. It belongs to the same outer boundary: logged once, and the whole run counts as failed.
        logger.error(
            "Run '%s' failed:\n%s",
            pipeline_run.run_id,
            _describe_contextual_data(artifact_sink_error),
            exc_info=artifact_sink_error,
            extra=_identify_run(pipeline_run),
        )
        return AnalysisOutcome(StepStatus.FAILED, failed_document_names)
    return AnalysisOutcome(StepStatus.FAILED if failed_document_names else StepStatus.COMPLETE, failed_document_names)


async def run_demo(demo_run_request: DemoRunRequest, *, logger: logging.Logger | None = None) -> DemoResult:
    """Run the system over the sample documents and return where the trail landed.

    The logger is a parameter, and the system shares just that one instance. Left out, the demo logs to
    the console through its own logger. When a caller supplies one (an acceptance test with a capturing
    handler, an application that already configured logging), the caller owns its handlers, level and
    propagation, and the demo only attaches its profile's handler for the duration of the run.
    """
    pages_by_document_name: Mapping[str, list[str]] = (
        SAMPLE_DOCUMENTS
        if demo_run_request.fail_page is None
        else with_malformed_reply(SAMPLE_DOCUMENTS, "Contract 12.pdf", demo_run_request.fail_page)
    )
    run_clock: Clock = demo_run_request.supplied_clock or Clock.create_system_clock()
    run_directory: Path = create_run_folder(demo_run_request.output_root, "batch", supplied_clock=run_clock)
    breadcrumb_formatter: BreadcrumbFormatter = BreadcrumbFormatter(time_display=demo_run_request.time_display)
    with ExitStack() as logging_scope:
        run_logger: logging.Logger = logger if logger is not None else logging_scope.enter_context(_console_logger(breadcrumb_formatter))
        # The profile chooses both where log lines go and where artifacts go. Every profile persists every
        # artifact: they are the record of what each step did, and what a later run could start from.
        artifact_destination: ArtifactDestination
        if demo_run_request.host_profile is HostProfile.LOCAL:
            logging_scope.enter_context(attached_run_log(run_logger, run_directory, breadcrumb_formatter))
            artifact_destination = _create_file_system_destination(run_directory)
        else:
            logging_scope.enter_context(attached_exception_telemetry(run_logger, run_directory / TELEMETRY_FILENAME))
            artifact_destination = _create_blob_storage_destination(demo_run_request.output_root, run_directory)
        async with DocumentAnalysisManager(ServiceLocatorDemo(demo_run_request.pace_seconds)) as document_analysis_manager:
            analysis_outcome: AnalysisOutcome = await _analyze_documents(
                pages_by_document_name, document_analysis_manager, artifact_destination.artifact_sink, run_logger, run_clock
            )
    return DemoResult(
        run_directory=run_directory,
        artifact_directory=artifact_destination.artifact_directory,
        run_status=analysis_outcome.run_status,
        failed_work_items=analysis_outcome.failed_work_items,
    )


def _default_output_root() -> Path:
    # main.py sits at <workspace>/apps/<app>/src/<module>/main.py.
    return Path(__file__).resolve().parents[4] / "artifacts"


def main() -> None:
    argument_parser: argparse.ArgumentParser = argparse.ArgumentParser(description="Run the Pipeline Breadcrumbs demo.")
    argument_parser.add_argument("--output", type=Path, default=_default_output_root(), help="Folder that receives one folder per run.")
    argument_parser.add_argument("--fail-page", type=int, default=None, help="Make Contract 12's model reply malformed on this zero-based page.")
    argument_parser.add_argument("--time", choices=[display.value for display in TimeDisplay], default=TimeDisplay.BOUNDARIES.value)
    argument_parser.add_argument(
        "--host",
        choices=[host_profile.value for host_profile in HostProfile],
        default=HostProfile.LOCAL.value,
        help="local writes a run log and the artifacts to disk; hosted uploads artifacts to blob storage and sends only exceptions to telemetry.",
    )
    arguments: argparse.Namespace = argument_parser.parse_args()
    try:
        demo_result: DemoResult = asyncio.run(
            run_demo(
                DemoRunRequest(
                    arguments.output,
                    fail_page=arguments.fail_page,
                    time_display=TimeDisplay(arguments.time),
                    host_profile=HostProfile(arguments.host),
                )
            ),
        )
    except InvalidFailPageError as invalid_fail_page_error:
        argument_parser.error(str(invalid_fail_page_error))
    if demo_result.run_status is StepStatus.FAILED:
        sys.exit(1)


if __name__ == "__main__":
    main()
