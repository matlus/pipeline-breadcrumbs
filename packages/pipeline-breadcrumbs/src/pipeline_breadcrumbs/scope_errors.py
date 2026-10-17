"""The exception the library raises when a work item scope is used outside the `async with` block that opens it.

A step used on a work item that was never entered records events for a work item the run never opened, so the run
fails as it closes, while building its manifest, far from the call that caused it, and loses the manifest of every
healthy work item with it. A step used after its work item closed files its events under a work item already reported
as finished. The scope refuses at the call instead. It subclasses `RuntimeError`, the standard type for an operation
that is invalid in the object's current state.
"""

from typing import final


@final
class WorkItemNotOpenError(RuntimeError):
    """A step was opened, entered, skipped or emitted from outside its work item's `async with` block."""
