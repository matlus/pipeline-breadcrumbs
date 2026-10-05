"""One place that turns the system's values into the JSON artifacts it emits."""

import json
from collections.abc import Iterable
from dataclasses import asdict

from pipeline_breadcrumbs_app.document_analysis.models import SectionRecord


def to_json_document(section_records: Iterable[SectionRecord]) -> bytes:
    """A JSON array with one object per record, each carrying the record's own field names."""
    return json.dumps([asdict(section_record) for section_record in section_records], indent=2).encode("utf-8")
