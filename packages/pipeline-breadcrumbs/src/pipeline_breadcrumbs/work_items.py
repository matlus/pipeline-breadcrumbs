"""The thing a pipeline run is working on."""

from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import final

from pipeline_breadcrumbs.declaration_errors import InvalidDeclarationError


@final
@dataclass(frozen=True, slots=True)
class WorkItem:
    """The unit of input a run processes.

    A work item can be a document, an incoming request, a row of a batch, a message from a
    queue, or anything else that has an identity and a name worth reading in a log. The
    library does not care which; it only needs the two values.

    `id` is a stable identifier (a UUID string, a key). `name` is the human-readable label
    and also seeds artifact filenames, so a file name such as `Contract 12.pdf` is a good fit.
    """

    id: str
    name: str

    def __post_init__(self) -> None:
        if not self.id.strip():
            raise InvalidDeclarationError(f"WorkItem id must not be blank (name {self.name!r})")
        if not self.name.strip():
            raise InvalidDeclarationError(f"WorkItem name must not be blank (id {self.id!r})")

    @property
    def stem(self) -> str:
        """The name without a file extension, used as the prefix of artifact filenames."""
        return PurePosixPath(self.name).stem or self.name
