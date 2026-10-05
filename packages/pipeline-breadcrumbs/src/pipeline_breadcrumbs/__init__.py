"""Pipeline Breadcrumbs: step-numbered progress logs and artifacts for long-running pipelines.

A pipeline opens steps on a scope. Each step announces itself, reports progress, hands
self-describing artifacts to a host-owned sink, and closes with its elapsed time and
outcome. The result is an ordered trail on disk that a person, or a coding assistant, can
read to find the first step whose output went wrong.
"""

from pipeline_breadcrumbs.artifacts import Artifact, ArtifactKind, ArtifactRole, ArtifactSink, RunArtifact, StepArtifact
from pipeline_breadcrumbs.attributes import AttributeBag, AttributeKey, AttributeValue, EventKind
from pipeline_breadcrumbs.breadcrumb_formatter import BreadcrumbFormatter, TimeDisplay
from pipeline_breadcrumbs.clock import Clock
from pipeline_breadcrumbs.errors import ArtifactSinkError, ContextualDataDict, ContextualExceptionProtocol
from pipeline_breadcrumbs.formatting import format_byte_size, format_elapsed
from pipeline_breadcrumbs.manifest import MANIFEST_KIND
from pipeline_breadcrumbs.pipeline_run import DEFAULT_LOGGER_NAME, PipelineRun
from pipeline_breadcrumbs.scopes import StepHostProtocol, StepScope, WorkItemScope
from pipeline_breadcrumbs.steps import Step, StepPath, StepStatus
from pipeline_breadcrumbs.work_items import WorkItem

__all__ = [
    "DEFAULT_LOGGER_NAME",
    "MANIFEST_KIND",
    "Artifact",
    "ArtifactKind",
    "ArtifactRole",
    "ArtifactSink",
    "ArtifactSinkError",
    "AttributeBag",
    "AttributeKey",
    "AttributeValue",
    "BreadcrumbFormatter",
    "Clock",
    "ContextualDataDict",
    "ContextualExceptionProtocol",
    "EventKind",
    "PipelineRun",
    "RunArtifact",
    "Step",
    "StepArtifact",
    "StepHostProtocol",
    "StepPath",
    "StepScope",
    "StepStatus",
    "TimeDisplay",
    "WorkItem",
    "WorkItemScope",
    "format_byte_size",
    "format_elapsed",
]
