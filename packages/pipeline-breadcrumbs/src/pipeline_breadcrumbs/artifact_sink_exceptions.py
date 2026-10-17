"""The exception a run raises when the host's sink cannot persist an artifact."""

from typing import final

from pipeline_breadcrumbs.artifacts import Artifact
from pipeline_breadcrumbs.exceptions import PipelineBreadcrumbsTechnicalBaseException


@final
class ArtifactSinkException(PipelineBreadcrumbsTechnicalBaseException):
    """The host's sink failed to persist an artifact.

    A storage outage is the host's problem, not a flaw in the step that produced the artifact, so it is
    technical and surfaces as its own exception carrying the artifact's identity. The original failure
    is the `__cause__`.
    """

    def __init__(self, artifact: Artifact) -> None:
        super().__init__(
            f"The artifact sink failed to persist '{artifact.filename}'",
            {
                "ArtifactKind": artifact.artifact_type,
                "ArtifactFilename": artifact.filename,
                "ArtifactBytes": len(artifact.content),
            },
        )
