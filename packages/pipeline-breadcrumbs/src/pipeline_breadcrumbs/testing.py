"""Helpers for acceptance tests of a pipeline built on the library.

Use `ArtifactRecorder` as the sink and `RecordCapture` as a logging handler, run the
pipeline, then assert which steps ran and which artifacts and attributes they produced.
Artifact presence is itself a signal: a remediation step that emits only when triggered is
diagnosed by whether its file exists.
"""

import logging
from typing import final, override

from pipeline_breadcrumbs.artifacts import Artifact, ArtifactKind, ArtifactSinkProtocol, StepArtifact
from pipeline_breadcrumbs.attributes import AttributeKey


@final
class ArtifactRecorder(ArtifactSinkProtocol):
    """An in-memory artifact sink. Pass the instance wherever a sink is expected."""

    def __init__(self) -> None:
        self.artifacts: list[Artifact] = []

    @override
    async def persist(self, artifact: Artifact) -> None:
        self.artifacts.append(artifact)

    def of_kind(self, artifact_kind: ArtifactKind) -> list[Artifact]:
        return [artifact for artifact in self.artifacts if artifact.artifact_kind == artifact_kind]

    def filenames(self) -> list[str]:
        return [artifact.filename for artifact in self.artifacts]

    def step_paths(self) -> list[str]:
        """The distinct step paths that emitted at least one artifact, in first-emitted order."""
        seen_step_paths: dict[str, None] = {}
        for artifact in self.artifacts:
            if isinstance(artifact, StepArtifact):
                seen_step_paths.setdefault(str(artifact.step_path), None)
        return list(seen_step_paths)


@final
class RecordCapture(logging.Handler):
    """A logging handler that keeps every record, for assertions on messages and attributes."""

    def __init__(self) -> None:
        super().__init__(level=logging.DEBUG)
        self.records: list[logging.LogRecord] = []

    @override
    def emit(self, record: logging.LogRecord) -> None:
        self.records.append(record)

    def boundaries(self, event: str | None = None) -> list[logging.LogRecord]:
        """Records that mark a run, work item or step boundary, optionally of one event kind."""
        return [
            record
            for record in self.records
            if AttributeKey.EVENT in record.__dict__ and (event is None or record.__dict__[AttributeKey.EVENT] == event)
        ]

    @staticmethod
    def attribute(record: logging.LogRecord, key: str) -> object:
        return record.__dict__.get(key)
