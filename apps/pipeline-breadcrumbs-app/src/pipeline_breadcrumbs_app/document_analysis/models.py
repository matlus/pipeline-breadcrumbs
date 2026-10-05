"""The values that flow between the system's steps."""

from dataclasses import dataclass
from typing import Final

CONFIDENCE_THRESHOLD: Final[float] = 0.7


@dataclass(frozen=True, slots=True)
class DetectedSection:
    """A section found on a page by the detection step."""

    page_number: int
    title: str


@dataclass(frozen=True, slots=True)
class ClassificationPrompt:
    """What the classification step asks the model about one section."""

    page_number: int
    title: str
    text: str


@dataclass(frozen=True, slots=True)
class ScoredSection:
    """A section with the model's category and how sure it is."""

    page_number: int
    title: str
    category: str
    confidence: float

    @property
    def needs_reconciliation(self) -> bool:
        return self.confidence < CONFIDENCE_THRESHOLD


@dataclass(frozen=True, slots=True)
class DocumentAnalysis:
    """What the system returns to its caller."""

    sections: list[ScoredSection]
    report: str


type SectionRecord = DetectedSection | ClassificationPrompt | ScoredSection
