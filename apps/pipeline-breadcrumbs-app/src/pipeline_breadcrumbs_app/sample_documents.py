"""The demo's input: two small documents, one page of text per list entry."""

from collections.abc import Mapping
from typing import Final

from pipeline_breadcrumbs_app.document_analysis.gateways.fake_model_gateway import MALFORMED_REPLY_MARKER

SAMPLE_DOCUMENTS: Final[dict[str, list[str]]] = {
    "Contract 12.pdf": [
        "SECTION: Definitions\nTerms used in this agreement.",
        "SECTION: Payment Terms\nInvoices are due in thirty days.",
        "SECTION: Miscellaneous\nNotices, assignment and the like.",
        "SECTION: Termination\nEither party may terminate with notice.",
    ],
    "Lease 4.pdf": [
        "SECTION: Premises\nThe leased property.",
        "SECTION: Rent\nMonthly rent and escalation.",
        "SECTION: Maintenance\nWho repairs what.",
    ],
}


class InvalidFailPageError(ValueError):
    """The page asked to fail does not exist in the document."""


def with_malformed_reply(pages_by_document_name: Mapping[str, list[str]], document_name: str, page_number: int) -> dict[str, list[str]]:
    """Mark one page so the fake model answers it with malformed JSON.

    The fault travels in the page text, which is visible in the page's own artifact, so the
    model gateway stays ignorant of which document it is serving.
    """
    page_count: int = len(pages_by_document_name.get(document_name, []))
    if not 0 <= page_number < page_count:
        raise InvalidFailPageError(f"Page {page_number} does not exist in '{document_name}', which has {page_count} page(s)")
    marked_pages_by_document_name: dict[str, list[str]] = {}
    source_document_name: str
    source_pages: list[str]
    for source_document_name, source_pages in pages_by_document_name.items():
        marked_pages_by_document_name[source_document_name] = list(source_pages)
    marked_pages_by_document_name[document_name][page_number] = (
        f"{marked_pages_by_document_name[document_name][page_number]}\n{MALFORMED_REPLY_MARKER}"
    )
    return marked_pages_by_document_name
