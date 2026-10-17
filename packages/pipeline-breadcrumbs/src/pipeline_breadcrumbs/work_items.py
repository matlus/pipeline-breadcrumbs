"""The thing a pipeline run is working on."""

from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import final

from pipeline_breadcrumbs.declaration_exceptions import InvalidDeclarationException
from pipeline_breadcrumbs.path_components import safe_path_component


@final
@dataclass(frozen=True, slots=True)
class WorkItem:
    """The unit of input a run processes.

    A work item can be a document, an incoming request, a row of a batch, a message from a
    queue, or anything else that has an identity and a name worth reading in a log. The
    library does not care which; it only needs the two values.

    `id` is a stable identifier (a UUID string, a key). `name` is the human-readable label
    and also seeds artifact filenames, so a file name such as `Contract 12.pdf` is a good fit.

    `file_stem` is for a name that is not a file name, such as the model identifier
    `typesafe/jev-1.13`, whose last dot is not an extension. When given, it is the artifact
    filename prefix exactly as written, so it must already be file-safe: pass
    `safe_path_component(name)` to keep the whole name.
    """

    id: str
    name: str
    file_stem: str | None = None

    def __post_init__(self) -> None:
        if not self.id.strip():
            raise InvalidDeclarationException(f"WorkItem id must not be blank (name {self.name!r})")
        if not self.name.strip():
            raise InvalidDeclarationException(f"WorkItem name must not be blank (id {self.id!r})")
        if self.file_stem is not None:
            _require_file_safe_stem(self.file_stem, self.id)

    @property
    def stem(self) -> str:
        """The prefix of artifact filenames, safe to store under on any common file system.

        It is `file_stem` when given. Otherwise it is the name without its file extension, with each
        character a file system refuses replaced by `_`, so `Q3: Plan / Draft.pdf` becomes `Q3_ Plan _ Draft`.
        """
        if self.file_stem is not None:
            return self.file_stem
        name_without_extension: str = PurePosixPath(safe_path_component(self.name)).stem
        return safe_path_component(name_without_extension)


def _require_file_safe_stem(file_stem: str, work_item_id: str) -> None:
    if not file_stem.strip():
        raise InvalidDeclarationException(f"WorkItem file_stem must not be blank (id {work_item_id!r})")
    file_safe_stem: str = safe_path_component(file_stem)
    if file_stem != file_safe_stem:
        raise InvalidDeclarationException(
            f"WorkItem file_stem {file_stem!r} must be safe to use as a file name, such as {file_safe_stem!r} (id {work_item_id!r})"
        )
