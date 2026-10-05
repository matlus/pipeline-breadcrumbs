"""The thing a pipeline run is working on."""

from dataclasses import dataclass
from pathlib import PurePath
from typing import final


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
            raise ValueError("WorkItem id must not be blank")
        if not self.name.strip():
            raise ValueError("WorkItem name must not be blank")

    @property
    def stem(self) -> str:
        """The name without a file extension, used as the prefix of artifact filenames."""
        return PurePath(self.name).stem or self.name
