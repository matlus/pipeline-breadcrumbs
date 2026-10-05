"""The artifact kinds the system produces, declared once.

Each key names what the file holds. A kind called `result` or `data` would be refused.
"""

from typing import Final

from pipeline_breadcrumbs import ArtifactKind, ArtifactRole

PAGE_TEXT: Final[ArtifactKind] = ArtifactKind("page_text", "txt", "text/plain")
RAW_DETECTION_RESPONSE: Final[ArtifactKind] = ArtifactKind("raw_detection_response", "txt", "text/plain")
DETECTED_SECTIONS: Final[ArtifactKind] = ArtifactKind("detected_sections", "json", "application/json")
CLASSIFICATION_PROMPTS: Final[ArtifactKind] = ArtifactKind("classification_prompts", "json", "application/json")
RAW_SCORE_RESPONSE: Final[ArtifactKind] = ArtifactKind("raw_score_response", "txt", "text/plain")
SECTION_SCORES: Final[ArtifactKind] = ArtifactKind("section_scores", "json", "application/json")
RAW_RECONCILIATION_RESPONSE: Final[ArtifactKind] = ArtifactKind("raw_reconciliation_response", "txt", "text/plain")
RECONCILED_SCORES: Final[ArtifactKind] = ArtifactKind("reconciled_scores", "json", "application/json")
ANALYSIS_REPORT: Final[ArtifactKind] = ArtifactKind("analysis_report", "md", "text/markdown", role=ArtifactRole.OUTPUT)


def page_discriminator(page_number: int) -> str:
    return f"page_{page_number:04d}"
