"""The exceptions the library raises when a scope is used outside the one `async with` block that opens it.

A step used on a work item that was never entered records events for a work item the run never opened, so the run
fails as it closes, while building its manifest, far from the call that caused it, and loses the manifest of every
healthy work item with it. A step used after its work item closed files its events under a work item already reported
as finished. The scope refuses at the call instead. No data the caller supplied causes it: the pipeline's code calls
the scope in the wrong order, and only its owner can correct that, so it is a technical exception.

A step scope entered a second time would file both openings under one record, so the second overwrites the first in
the manifest and can report the first opening's outcome as its own. Each opening of a step needs its own scope, from
its own `step(...)` call, and the scope refuses a second entry for the same technical reason.
"""

from typing import final

from pipeline_breadcrumbs.exceptions import PipelineBreadcrumbsTechnicalBaseException


@final
class WorkItemNotOpenException(PipelineBreadcrumbsTechnicalBaseException):
    """A step was opened, entered, skipped or emitted from outside its work item's `async with` block."""


@final
class StepAlreadyEnteredException(PipelineBreadcrumbsTechnicalBaseException):
    """A step scope was entered with `async with` a second time; each opening of a step needs its own `step(...)` call."""
