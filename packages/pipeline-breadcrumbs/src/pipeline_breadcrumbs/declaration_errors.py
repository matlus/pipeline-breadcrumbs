"""The one exception the library raises for a declaration it refuses.

A step, an artifact kind, a work item or a run declared with a value the trail could not carry (a blank
name, a step number outside the padded range, a vague artifact key, a discriminator unsafe in a filename)
is refused the moment it is declared. It subclasses `ValueError`, so a caller that catches that still does.
"""

from typing import final


@final
class InvalidDeclarationError(ValueError):
    """A pipeline declared a step, artifact kind, work item or run with a value the library refuses."""
