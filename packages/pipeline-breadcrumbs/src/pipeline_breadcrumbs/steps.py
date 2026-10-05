"""Step identity: what a step is called, where it sits, and how it ended."""

import re
from dataclasses import InitVar, dataclass, field
from enum import StrEnum
from typing import Final, final, override

MAX_STEP_NUMBER: Final[int] = 99

_KEY_PATTERN: Final[re.Pattern[str]] = re.compile(r"[a-z0-9]+(?:_[a-z0-9]+)*")
_NON_KEY_CHARACTERS: Final[re.Pattern[str]] = re.compile(r"[^a-z0-9]+")


class StepStatus(StrEnum):
    """The closed set of states a boundary record can announce."""

    STARTED = "STARTED"
    COMPLETE = "COMPLETE"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"


@final
@dataclass(frozen=True, slots=True)
class Step:
    """A step, declared once.

    `step_number` is relative to the step's parent: a pipeline's top-level steps are 1, 2, 3,
    and a step declared as 2 inside parent step 3 is reported everywhere as 3.2. The same
    engine can therefore run as a whole pipeline or nested inside another step without
    changing its declarations.

    `key` is the stable machine name. Dashboards and alerts should key on it, never on the
    number, so renumbering a pipeline breaks nothing. It is derived from `name` unless a
    `requested_key` is given, so it is always a validated, non-empty string.
    """

    step_number: int
    name: str
    requested_key: InitVar[str | None] = None
    key: str = field(init=False)

    def __post_init__(self, requested_key: str | None) -> None:
        if not 1 <= self.step_number <= MAX_STEP_NUMBER:
            raise ValueError(f"Step number must be between 1 and {MAX_STEP_NUMBER}, got {self.step_number}")
        display_name: str = self.name.strip()
        if not display_name:
            raise ValueError("Step name must not be blank")
        resolved_key: str = requested_key if requested_key is not None else _NON_KEY_CHARACTERS.sub("_", display_name.lower()).strip("_")
        if not _KEY_PATTERN.fullmatch(resolved_key):
            raise ValueError(f"Step key '{resolved_key}' must be lowercase letters and digits separated by single underscores")
        object.__setattr__(self, "name", display_name)
        object.__setattr__(self, "key", resolved_key)


@final
@dataclass(frozen=True, slots=True, order=True)
class StepPath:
    """The absolute position of a step: the numbers from the outermost step down to it.

    The path is a tuple of integers, so 2.10 sorts after 2.9. It is never parsed from text
    and never converted through a float.
    """

    step_numbers: tuple[int, ...] = ()

    def child(self, step_number: int) -> StepPath:
        return StepPath((*self.step_numbers, step_number))

    @property
    def depth(self) -> int:
        return len(self.step_numbers)

    def padded(self) -> str:
        """The path with each segment zero-padded, for filenames that must sort in pipeline order."""
        return ".".join(f"{step_number:02d}" for step_number in self.step_numbers)

    @override
    def __str__(self) -> str:
        return ".".join(str(step_number) for step_number in self.step_numbers)
