"""The shared machinery behind every scope in one run.

Internal to the library: hosts and pipelines work with `PipelineRun`, `WorkItemScope`
and `StepScope`, never with this class.
"""

import logging
from collections.abc import Mapping
from typing import final

from pipeline_breadcrumbs.artifacts import Artifact, ArtifactSinkProtocol
from pipeline_breadcrumbs.attributes import AttributeBag, AttributeValue
from pipeline_breadcrumbs.clock import Clock
from pipeline_breadcrumbs.errors import ArtifactSinkError
from pipeline_breadcrumbs.manifest import RunRecorder


@final
class RunContext:
    """The sink, the logger, the clock, the run recorder and the attributes every record carries."""

    def __init__(
        self,
        *,
        artifact_sink: ArtifactSinkProtocol,
        logger: logging.Logger,
        base_attributes: AttributeBag,
        clock: Clock,
        run_recorder: RunRecorder,
    ) -> None:
        self.logger: logging.Logger = logger
        self.clock: Clock = clock
        self.run_recorder: RunRecorder = run_recorder
        self._artifact_sink: ArtifactSinkProtocol = artifact_sink
        self._base_attributes: AttributeBag = base_attributes

    def log(self, level: int, message: str, attributes: Mapping[str, AttributeValue]) -> None:
        merged_attributes: AttributeBag = {**self._base_attributes, **attributes}
        self.logger.log(level, message, extra=merged_attributes)

    async def persist(self, artifact: Artifact) -> None:
        """Hand an artifact to the host's sink, translating any failure into `ArtifactSinkError`."""
        try:
            await self._artifact_sink.persist(artifact)
        except Exception as error:
            raise ArtifactSinkError(artifact) from error
