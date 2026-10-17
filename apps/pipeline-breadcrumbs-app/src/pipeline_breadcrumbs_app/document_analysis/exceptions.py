"""The system's exceptions.

A real host brings its own hierarchy (the Meridian base exception, for instance). This
minimal one has the same shape: a message, named contextual data, and `add_contextual_data`
so the failing step can stamp its identity onto it. That shape is all the library asks for.
"""

from abc import ABC
from typing import final

from pipeline_breadcrumbs import ContextualDataDict


class DocumentAnalysisError(Exception, ABC):
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


class DocumentAnalysisBusinessError(DocumentAnalysisError, ABC):
    """The caller can correct this: the request itself was wrong, and sending it again unchanged fails the same way."""


class DocumentAnalysisTechnicalError(DocumentAnalysisError, ABC):
    """An operator or a dependency owns this: the request was fine, and something the system relies on failed or is misconfigured."""


@final
class DocumentValidationError(DocumentAnalysisBusinessError):
    """The document handed to the system is not one it can analyze. Every problem found is reported at once."""

    def __init__(self, validation_problems: list[str], contextual_data_by_name: ContextualDataDict | None = None) -> None:
        super().__init__(f"The document cannot be analyzed: {'; '.join(validation_problems)}", contextual_data_by_name)


@final
class ModelResponseParseError(DocumentAnalysisTechnicalError):
    """The model returned something that is not the JSON the step asked for."""

    def __init__(self, page_number: int, reason: str) -> None:
        super().__init__(f"The model response for page {page_number} could not be parsed: {reason}", {"PageNumber": page_number})


@final
class ConfigurationSettingError(DocumentAnalysisTechnicalError):
    """A configuration setting is missing or malformed. Raised while the system is being built, before any work."""

    def __init__(self, message: str, environment_variable_name: str) -> None:
        super().__init__(message, {"Configuration.EnvironmentVariableName": environment_variable_name})


@final
class ModelServiceUnavailableError(DocumentAnalysisTechnicalError):
    """The model service could not answer: it was unreachable, timed out, was busy, or failed on its side.

    A later attempt might succeed. The system does not retry; the step fails and its breadcrumbs show where.
    """

    def __init__(self, operation_name: str, failure_detail: str, http_status_code: int | None = None) -> None:
        contextual_data_by_name: ContextualDataDict = {"ModelService.Operation": operation_name, "ModelService.FailureDetail": failure_detail}
        if http_status_code is not None:
            # Only a response carries a status; an unreachable service or a timeout has none to report.
            contextual_data_by_name["ModelService.HttpStatusCode"] = http_status_code
        super().__init__(f"The model service could not answer the '{operation_name}' request: {failure_detail}", contextual_data_by_name)


@final
class ModelServiceRequestRejectedError(DocumentAnalysisTechnicalError):
    """The model service refused the request itself. Sending it again would be refused again."""

    def __init__(self, operation_name: str, http_status_code: int, failure_detail: str) -> None:
        super().__init__(
            f"The model service rejected the '{operation_name}' request with HTTP {http_status_code}: {failure_detail}",
            {"ModelService.Operation": operation_name, "ModelService.HttpStatusCode": http_status_code, "ModelService.FailureDetail": failure_detail},
        )


@final
class ModelServiceContractError(DocumentAnalysisTechnicalError):
    """The model service answered successfully but not in the envelope its API promises.

    This is the service breaking its contract, not the model giving a bad answer: the model's own reply is
    untrusted text that the processors check, and its faults are `ModelResponseParseError`.
    """

    def __init__(self, operation_name: str, failure_detail: str) -> None:
        super().__init__(
            f"The model service answered the '{operation_name}' request in an unexpected shape: {failure_detail}",
            {"ModelService.Operation": operation_name, "ModelService.FailureDetail": failure_detail},
        )
