"""The exception the library raises when a work item scope is used outside the `async with` block that opens it.

A step opened on a work item that was never entered, or that has already closed, would record events for a
work item the run never opened. The run would then fail as it closes, while building its manifest, far from the
call that caused it, and lose the manifest of every healthy work item with it. The scope refuses at the call instead.
It subclasses `RuntimeError`, the standard type for an operation that is invalid in the object's current state.
"""

from typing import final


@final
class WorkItemNotOpenError(RuntimeError):
    """A step was opened or skipped on a work item scope outside its `async with` block."""
