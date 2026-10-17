"""The sample's one exception hierarchy: a root, a business branch and a technical branch.

A system owns exactly one exception hierarchy, named for it. Code copied from this sample, whole or
class by class, becomes part of the receiving system, so every exception here descends through one of
the two branches. A receiving system renames the root for itself, or reparents the branches onto its
own root, and nothing else changes.

- Business: the caller can correct it. The request or the data it carried was wrong, and sending it
  again unchanged fails the same way.
- Technical: the system's owner must correct it. The request was fine, and the code, a dependency or
  the configuration the system relies on failed.

Every exception carries a message and named contextual data, and accumulates more as it propagates:
the failing step stamps its identity onto it, and each boundary it crosses may add what that boundary
knows. A step stamps any exception of that shape, `ContextualExceptionProtocol`, so an exception from
another hierarchy shaped the same way (such as the Meridian application base exception) is stamped too.
"""

from abc import ABC
from typing import Final, Protocol, final, runtime_checkable

type ContextualDataDict = dict[str, str | int | float | bool]

FAILED_AT_STEP_NUMBER_KEY: Final[str] = "FailedAtStepNumber"
FAILED_AT_STEP_NAME_KEY: Final[str] = "FailedAtStepName"
FAILED_AT_STEP_KEY_KEY: Final[str] = "FailedAtStepKey"


@runtime_checkable
class ContextualExceptionProtocol(Protocol):
    @property
    def contextual_data_by_name(self) -> ContextualDataDict: ...

    def add_contextual_data(self, contextual_data_by_name: ContextualDataDict) -> None: ...


class PipelineBreadcrumbsBaseException(Exception, ABC):
    """The root of the sample's exceptions. Abstract, as are its two branches: only a `@final` concrete exception is raised."""

    def __init__(self, message: str, contextual_data_by_name: ContextualDataDict | None = None) -> None:
        # CPython does not enforce ABC abstractness for exception classes, so the rule is enforced here.
        if not getattr(type(self), "__final__", False):
            raise AbstractExceptionRaisedException(f"{type(self).__name__} is abstract; raise a concrete @final exception that descends from it")
        super().__init__(message)
        self._message: str = message
        self._contextual_data_by_name: ContextualDataDict = dict(contextual_data_by_name or {})

    @property
    def contextual_data_by_name(self) -> ContextualDataDict:
        return {"ExceptionType": type(self).__name__, "Message": self._message, **self._contextual_data_by_name}

    def add_contextual_data(self, contextual_data_by_name: ContextualDataDict) -> None:
        self._contextual_data_by_name.update(contextual_data_by_name)


class PipelineBreadcrumbsBusinessBaseException(PipelineBreadcrumbsBaseException, ABC):
    """The caller can correct this: the request itself was wrong, and sending it again unchanged fails the same way."""


class PipelineBreadcrumbsTechnicalBaseException(PipelineBreadcrumbsBaseException, ABC):
    """The system's owner must correct this: the request was fine, and something the system relies on failed or is misused."""


@final
class AbstractExceptionRaisedException(PipelineBreadcrumbsTechnicalBaseException):
    """Code raised one of the abstract bases instead of a concrete exception that names the failure.

    Only the code's owner can correct that, so it is technical. Being `@final`, it passes the guard it is raised from.
    """
