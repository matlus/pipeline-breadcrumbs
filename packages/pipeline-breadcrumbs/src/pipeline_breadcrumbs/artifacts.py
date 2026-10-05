"""Artifacts: self-describing files a step hands to the host.

An artifact is the physical output of a step: a JSON document, an extracted image, a
report. Most are interim captures whose first job is observability; some are the real
output. Either way the step never knows where the file lands. It emits the artifact and
the host's sink persists it.

There are two kinds of artifact. A `StepArtifact` belongs to one step of one work item. A
`RunArtifact`, such as the run manifest, belongs to the run as a whole. Each derives its own
filename, so no caller composes names.
"""

import re
from dataclasses import dataclass
from enum import StrEnum
from typing import Final, Protocol, final

from pipeline_breadcrumbs.steps import StepPath
from pipeline_breadcrumbs.work_items import WorkItem

_KIND_KEY_PATTERN: Final[re.Pattern[str]] = re.compile(r"[a-z][a-z0-9]*(?:_[a-z0-9]+)*")
_EXTENSION_PATTERN: Final[re.Pattern[str]] = re.compile(r"[a-z0-9]+")
_DISCRIMINATOR_PATTERN: Final[re.Pattern[str]] = re.compile(r"[A-Za-z0-9._-]+")

# Names that say nothing about what the file holds. A kind named for its role in the
# pipeline ("page_evidence") can be found again; a kind named "result" cannot.
VAGUE_KIND_KEYS: Final[frozenset[str]] = frozenset({"result", "results", "output", "outputs", "data", "artifact", "artifacts", "payload"})


class ArtifactRole(StrEnum):
    """Whether an artifact is captured working data or a deliverable."""

    INTERIM = "interim"
    OUTPUT = "output"


@final
@dataclass(frozen=True, slots=True)
class ArtifactKind:
    """A declared kind of artifact. A pipeline declares its kinds once, as constants.

    `key` names what the file holds, so it must be self-describing. Vague keys such as
    `result` or `data` are refused when the kind is constructed.
    """

    key: str
    extension: str
    content_type: str
    role: ArtifactRole = ArtifactRole.INTERIM

    def __post_init__(self) -> None:
        if not _KIND_KEY_PATTERN.fullmatch(self.key):
            raise ValueError(f"Artifact kind key '{self.key}' must be lowercase words separated by single underscores")
        if self.key in VAGUE_KIND_KEYS:
            raise ValueError(f"Artifact kind key '{self.key}' is too vague; name the kind for what the file holds, such as 'page_evidence'")
        if not _EXTENSION_PATTERN.fullmatch(self.extension):
            raise ValueError(f"Artifact extension '{self.extension}' must be lowercase letters and digits, without a dot")
        if not self.content_type.strip():
            raise ValueError("Artifact content type must not be blank")


@final
@dataclass(frozen=True, slots=True)
class StepArtifact:
    """An artifact one step produced for one work item: everything a sink needs to persist it without asking."""

    artifact_kind: ArtifactKind
    content: bytes
    work_item: WorkItem
    step_path: StepPath
    discriminator: str | None = None

    def __post_init__(self) -> None:
        if self.step_path.depth == 0:
            raise ValueError("A step artifact needs a non-empty step path")
        if self.discriminator is not None and not _DISCRIMINATOR_PATTERN.fullmatch(self.discriminator):
            raise ValueError(f"Artifact discriminator '{self.discriminator}' may contain only letters, digits, dot, underscore and hyphen")

    @property
    def artifact_type(self) -> str:
        """The name of what the file holds, such as `page_evidence`."""
        return self.artifact_kind.key

    @property
    def content_type(self) -> str:
        return self.artifact_kind.content_type

    @property
    def filename(self) -> str:
        """For example `Contract 12_step_02.03_metadata_audit_page_0003.json`.

        Step segments are zero-padded so a directory listing sorts in pipeline order,
        including past step 9.
        """
        discriminator_part: str = f"_{self.discriminator}" if self.discriminator else ""
        return f"{self.work_item.stem}_step_{self.step_path.padded()}_{self.artifact_kind.key}{discriminator_part}.{self.artifact_kind.extension}"


@final
@dataclass(frozen=True, slots=True)
class RunArtifact:
    """An artifact that belongs to the run as a whole, such as the run manifest."""

    artifact_kind: ArtifactKind
    content: bytes

    @property
    def artifact_type(self) -> str:
        """The name of what the file holds, such as `manifest`."""
        return self.artifact_kind.key

    @property
    def content_type(self) -> str:
        return self.artifact_kind.content_type

    @property
    def filename(self) -> str:
        return f"{self.artifact_kind.key}.{self.artifact_kind.extension}"


type Artifact = StepArtifact | RunArtifact


class ArtifactSinkProtocol(Protocol):
    """Where a run's artifacts go. The application builds one implementation and hands it to `PipelineRun`.

    An implementation owns whatever it needs to persist: a run directory and the folders it has
    claimed, a blob container client, a connection. The application chooses which implementation
    to hand in, the way it chooses any other service it composes, and a test hands in an in-memory
    one. A step never calls the sink directly; it emits through a scope.

    `persist` raises whatever error is natural for the destination. The run wraps it in
    `ArtifactSinkError` and keeps the artifact's identity on it.
    """

    async def persist(self, artifact: Artifact) -> None: ...
