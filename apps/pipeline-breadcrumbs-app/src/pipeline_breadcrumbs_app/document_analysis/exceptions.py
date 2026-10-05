"""The system's exceptions.

A real host brings its own hierarchy (the Meridian base exception, for instance). This
minimal one has the same shape: a message, named contextual data, and `add_contextual_data`
so the failing step can stamp its identity onto it. That shape is all the library asks for.
"""

from typing import final

from pipeline_breadcrumbs import ContextualDataDict


class DocumentAnalysisError(Exception):
    """A technical failure in the document analysis system, carrying named diagnostic data.

    Like the host exception bases it mirrors, it accumulates contextual data as it propagates:
    each boundary it crosses may add what that boundary knows.
    """

    def __init__(self, message: str, contextual_data_by_name: ContextualDataDict | None = None) -> None:
        super().__init__(message)
        self._message: str = message
        self._contextual_data_by_name: ContextualDataDict = dict(contextual_data_by_name or {})

    @property
    def contextual_data_by_name(self) -> ContextualDataDict:
        return {"ExceptionType": type(self).__name__, "Message": self._message, **self._contextual_data_by_name}

    def add_contextual_data(self, contextual_data_by_name: ContextualDataDict) -> None:
        self._contextual_data_by_name.update(contextual_data_by_name)

    def describe(self) -> str:
        return "\n".join(f"  {name}: {value}" for name, value in self.contextual_data_by_name.items())


@final
class DocumentValidationError(DocumentAnalysisError):
    """The document handed to the system is not one it can analyze. Every problem found is reported at once."""

    def __init__(self, validation_problems: list[str], contextual_data_by_name: ContextualDataDict | None = None) -> None:
        super().__init__(f"The document cannot be analyzed: {'; '.join(validation_problems)}", contextual_data_by_name)


@final
class ModelResponseParseError(DocumentAnalysisError):
    """The model returned something that is not the JSON the step asked for."""

    def __init__(self, page_number: int, reason: str) -> None:
        super().__init__(f"The model response for page {page_number} could not be parsed: {reason}", {"PageNumber": page_number})
