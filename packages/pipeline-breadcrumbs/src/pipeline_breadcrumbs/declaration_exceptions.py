"""The one exception the library raises for a declaration it refuses.

A step, an artifact kind, a work item or a run declared with a value the trail could not carry (a blank
name, a step number outside the padded range, a vague artifact key, a discriminator unsafe in a filename)
is refused the moment it is declared. The caller supplied the value and can correct it, often from the
data it was given (a document's name, say), so it is a business exception.
"""

from typing import final

from pipeline_breadcrumbs.exceptions import PipelineBreadcrumbsBusinessBaseException


@final
class InvalidDeclarationException(PipelineBreadcrumbsBusinessBaseException):
    """A pipeline declared a step, artifact kind, work item or run with a value the library refuses."""
