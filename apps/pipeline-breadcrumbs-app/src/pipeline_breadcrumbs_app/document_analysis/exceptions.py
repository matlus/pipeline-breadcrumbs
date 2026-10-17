"""The system's exceptions, on the sample's one hierarchy.

Each derives from the business or the technical branch the package defines, so the application, the
library and the system it calls share one root. The failing step stamps its identity onto any of them.
"""

from collections.abc import Iterable
from typing import final

from pipeline_breadcrumbs import ContextualDataDict, PipelineBreadcrumbsBusinessBaseException, PipelineBreadcrumbsTechnicalBaseException


@final
class DocumentValidationException(PipelineBreadcrumbsBusinessBaseException):
    """The document handed to the system is not one it can analyze. Every problem found is reported at once."""

    def __init__(self, validation_problems: Iterable[str], contextual_data_by_name: ContextualDataDict) -> None:
        super().__init__(f"The document cannot be analyzed: {'; '.join(validation_problems)}", contextual_data_by_name)


@final
class ModelResponseParseException(PipelineBreadcrumbsTechnicalBaseException):
    """The model returned something that is not the JSON the step asked for."""

    def __init__(self, page_number: int, reason: str) -> None:
        super().__init__(f"The model response for page {page_number} could not be parsed: {reason}", {"PageNumber": page_number})


@final
class ConfigurationSettingException(PipelineBreadcrumbsTechnicalBaseException):
    """A configuration setting is missing or malformed. Raised while the system is being built, before any work."""

    def __init__(self, message: str, environment_variable_name: str) -> None:
        super().__init__(message, {"Configuration.EnvironmentVariableName": environment_variable_name})


@final
class ModelServiceUnavailableException(PipelineBreadcrumbsTechnicalBaseException):
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
class ModelServiceRequestRejectedException(PipelineBreadcrumbsTechnicalBaseException):
    """The model service refused the request itself. Sending it again would be refused again."""

    def __init__(self, operation_name: str, http_status_code: int, failure_detail: str) -> None:
        super().__init__(
            f"The model service rejected the '{operation_name}' request with HTTP {http_status_code}: {failure_detail}",
            {"ModelService.Operation": operation_name, "ModelService.HttpStatusCode": http_status_code, "ModelService.FailureDetail": failure_detail},
        )


@final
class ModelServiceContractException(PipelineBreadcrumbsTechnicalBaseException):
    """The model service answered successfully but not in the envelope its API promises.

    This is the service breaking its contract, not the model giving a bad answer: the model's own reply is
    untrusted text that the processors check, and its faults are `ModelResponseParseException`.
    """

    def __init__(self, operation_name: str, failure_detail: str) -> None:
        super().__init__(
            f"The model service answered the '{operation_name}' request in an unexpected shape: {failure_detail}",
            {"ModelService.Operation": operation_name, "ModelService.FailureDetail": failure_detail},
        )
