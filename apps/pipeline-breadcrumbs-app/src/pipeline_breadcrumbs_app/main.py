"""The demo application: the thing that calls the system. It is not part of the system.

The system is `DocumentAnalysisManager`. This module is the application around it, and it makes
every decision the system must not make:

* where artifacts go: it implements the artifact callback. Every artifact is persisted, wherever the
  application runs, because artifacts are the record of what each step did;
* where log lines go: it builds the one logger the system shares and decides which handlers listen
  to it. That is the only thing a local run and a hosted run do differently;
* what to run and what to do when it fails: it opens the run, opens one work item per document,
  calls the system, and logs a failure once, at this outer boundary.

The system receives the callback and the logger through the scope it is handed, and never sees
a path or a handler.

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
    ArtifactSink,
    AttributeKey,
    BreadcrumbFormatter,
    PipelineRun,
    TimeDisplay,
    WorkItem,
    WorkItemScope,
)
from pipeline_breadcrumbs.hosting import FileSystemArtifactSink, attached_run_log, create_run_folder
from pipeline_breadcrumbs_app.document_analysis.document_analysis_manager import DocumentAnalysisManager
from pipeline_breadcrumbs_app.document_analysis.exceptions import DocumentAnalysisError
from pipeline_breadcrumbs_app.document_analysis.gateways.fake_model_gateway import FakeModelGateway
from pipeline_breadcrumbs_app.document_analysis.simulated_work import SimulatedWork
from pipeline_breadcrumbs_app.sample_documents import SAMPLE_DOCUMENTS, InvalidFailPageError, with_malformed_reply
from pipeline_breadcrumbs_app.telemetry import TELEMETRY_FILENAME, attached_exception_telemetry

PIPELINE_NAME: Final[str] = "document-analysis-demo"
LOGGER_NAME: Final[str] = "pipeline_breadcrumbs_app"

# How long a simulated model call takes. Other simulated work takes a third of it. The delay is
# there so a person watching sees the flow go from step to step; fifteen lines arriving in one
# second explain nothing. It is not a command-line switch, because a teaching sample should need
# no switches to read well. Tests pass 0 to `run_demo` and run instantly.
DEFAULT_PACE_SECONDS: Final[float] = 0.3


class HostProfile(StrEnum):
    """Where the application runs. The system behaves the same in both; only the log handlers differ.

    Local keeps every informational line in a `run.log` beside the artifacts, for a developer who is
    watching the run. Hosted leaves informational lines to the platform's own process logs (the console
    here) and sends only exceptions to telemetry, the way an Azure ML pipeline reports to Application Insights.
    """

    LOCAL = "local"
    HOSTED = "hosted"


@dataclass(frozen=True, slots=True)
class DemoResult:
    run_directory: Path
    failed_work_items: list[str]


def _create_artifact_callback(run_directory: Path) -> ArtifactSink:
    """The application's persistence callback. The system only ever sees `ArtifactSink`.

    It persists every artifact: they are the record of what each step did, and they are what a later
    run could start from. A hosted application would hand the system a blob-storage sink here; this
    one writes to disk so the demo needs nothing else.
    """
    return FileSystemArtifactSink(run_directory)


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


async def _analyze_documents(
    pages_by_document_name: Mapping[str, list[str]],
    document_analysis_manager: DocumentAnalysisManager,
    artifact_callback: ArtifactSink,
    logger: logging.Logger,
) -> list[str]:
    """Run every document through the system and return the names of those that failed."""
    failed_document_names: list[str] = []
    document_name: str
    pages: list[str]
    async with PipelineRun(name=PIPELINE_NAME, sink=artifact_callback, logger=logger) as pipeline_run:
        for document_name, pages in pages_by_document_name.items():
            try:
                work_item_scope: WorkItemScope
                async with pipeline_run.work_item(WorkItem(id=str(uuid4()), name=document_name)) as work_item_scope:
                    await document_analysis_manager.analyze_document(work_item_scope, pages)
            except DocumentAnalysisError as document_analysis_error:
                # The application's single outer boundary: the exception is logged once, with its
                # traceback and every named fact it carries. Steps only leave breadcrumbs. The run and
                # work item identity travel as attributes, so telemetry can tell which run this was.
                logger.error(
                    "Work item '%s' failed:\n%s",
                    document_name,
                    document_analysis_error.describe(),
                    exc_info=document_analysis_error,
                    extra={
                        AttributeKey.PIPELINE_NAME: PIPELINE_NAME,
                        AttributeKey.RUN_ID: pipeline_run.run_id,
                        AttributeKey.WORK_ITEM_NAME: document_name,
                    },
                )
                failed_document_names.append(document_name)
    return failed_document_names


async def run_demo(
    output_root: Path,
    *,
    fail_page: int | None = None,
    time_display: TimeDisplay = TimeDisplay.BOUNDARIES,
    logger: logging.Logger | None = None,
    host_profile: HostProfile = HostProfile.LOCAL,
    pace_seconds: float = DEFAULT_PACE_SECONDS,
) -> DemoResult:
    """Run the system over the sample documents and return where the trail landed.

    The logger is a parameter, and the system shares just that one instance. Left out, the demo logs to
    the console through its own logger. When a caller supplies one (an acceptance test with a capturing
    handler, an application that already configured logging), the caller owns its handlers, level and
    propagation, and the demo only attaches its profile's handler for the duration of the run.

    `pace_seconds` is how long a simulated model call takes; other simulated work takes a third of
    that. The default makes the log readable as it appears; a test passes 0 to run instantly.
    """
    pages_by_document_name: Mapping[str, list[str]] = (
        SAMPLE_DOCUMENTS if fail_page is None else with_malformed_reply(SAMPLE_DOCUMENTS, "Contract 12.pdf", fail_page)
    )
    run_directory: Path = create_run_folder(output_root, "batch")
    breadcrumb_formatter: BreadcrumbFormatter = BreadcrumbFormatter(time_display=time_display)
    document_analysis_manager: DocumentAnalysisManager = DocumentAnalysisManager(FakeModelGateway(pace_seconds), SimulatedWork(pace_seconds / 3))
    with ExitStack() as logging_scope:
        run_logger: logging.Logger = logger if logger is not None else logging_scope.enter_context(_console_logger(breadcrumb_formatter))
        if host_profile is HostProfile.LOCAL:
            logging_scope.enter_context(attached_run_log(run_logger, run_directory, breadcrumb_formatter))
        else:
            logging_scope.enter_context(attached_exception_telemetry(run_logger, run_directory / TELEMETRY_FILENAME))
        failed_work_items: list[str] = await _analyze_documents(
            pages_by_document_name, document_analysis_manager, _create_artifact_callback(run_directory), run_logger
        )
    return DemoResult(run_directory=run_directory, failed_work_items=failed_work_items)


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
        help="local writes a run log beside the artifacts; hosted sends only exceptions to telemetry.",
    )
    arguments: argparse.Namespace = argument_parser.parse_args()
    try:
        demo_result: DemoResult = asyncio.run(
            run_demo(
                arguments.output,
                fail_page=arguments.fail_page,
                time_display=TimeDisplay(arguments.time),
                host_profile=HostProfile(arguments.host),
            ),
        )
    except InvalidFailPageError as invalid_fail_page_error:
        argument_parser.error(str(invalid_fail_page_error))
    if demo_result.failed_work_items:
        sys.exit(1)


if __name__ == "__main__":
    main()
