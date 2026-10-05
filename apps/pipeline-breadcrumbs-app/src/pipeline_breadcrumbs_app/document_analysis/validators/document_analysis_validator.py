"""Front-door validation for the document analysis system."""

from collections.abc import Sequence
from typing import final

from pipeline_breadcrumbs_app.document_analysis.exceptions import DocumentValidationError


@final
class DocumentAnalysisValidator:
    """Refuses a document the system cannot analyze, naming every problem at once."""

    @staticmethod
    def validate(pages: Sequence[str]) -> None:
        validation_problems: list[str] = []
        if not pages:
            validation_problems.append("the document has no pages; supply at least one page of text")
        blank_page_numbers: list[int] = [page_number for page_number, page_text in enumerate(pages) if not page_text.strip()]
        if blank_page_numbers:
            validation_problems.append(f"pages {blank_page_numbers} are blank; every page needs text")
        if validation_problems:
            raise DocumentValidationError(validation_problems, {"PageCount": len(pages)})
