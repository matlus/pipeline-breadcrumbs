"""Exception support: how the library meets the host's exception hierarchy.

The library owns no exception base class. An exception takes part in step diagnostics by
shape alone: if it exposes `contextual_data_by_name` and `add_contextual_data` (as the
Meridian application base exception does), the failing step stamps its identity onto it.
"""

from typing import Final, Protocol, final, runtime_checkable

from pipeline_breadcrumbs.artifacts import Artifact

type ContextualDataDict = dict[str, str | int | float | bool]

FAILED_AT_STEP_NUMBER_KEY: Final[str] = "FailedAtStepNumber"
FAILED_AT_STEP_NAME_KEY: Final[str] = "FailedAtStepName"
FAILED_AT_STEP_KEY_KEY: Final[str] = "FailedAtStepKey"


@runtime_checkable
class ContextualExceptionProtocol(Protocol):
    @property
    def contextual_data_by_name(self) -> ContextualDataDict: ...

    def add_contextual_data(self, contextual_data_by_name: ContextualDataDict) -> None: ...


@final
class ArtifactSinkError(Exception):
    """The host's sink failed to persist an artifact.

    A storage outage is the host's problem, not a flaw in the step that produced the
    artifact, so it surfaces as its own exception carrying the artifact's identity. The
    original failure is the `__cause__`. This is a technical exception: translate it to
    the host's own technical exception type at the host boundary if one exists.

    Like the host exception bases it mirrors, it accumulates contextual data as it
    propagates: each boundary it crosses may add what that boundary knows.
    """

    def __init__(self, artifact: Artifact) -> None:
        super().__init__(f"The artifact sink failed to persist '{artifact.filename}'")
        self._contextual_data_by_name: ContextualDataDict = {
            "ExceptionType": type(self).__name__,
            "ArtifactKind": artifact.artifact_type,
            "ArtifactFilename": artifact.filename,
            "ArtifactBytes": len(artifact.content),
        }

    @property
    def contextual_data_by_name(self) -> ContextualDataDict:
        return dict(self._contextual_data_by_name)

    def add_contextual_data(self, contextual_data_by_name: ContextualDataDict) -> None:
        self._contextual_data_by_name.update(contextual_data_by_name)
