import json
from typing import TypedDict, cast


class StepRecordDocument(TypedDict):
    step_path: str
    step_key: str
    step_name: str
    step_status: str
    started_at: str
    elapsed_seconds: float | None
    outcome: str | None
    failure: str | None


class ArtifactRecordDocument(TypedDict):
    filename: str
    artifact_type: str
    role: str
    byte_count: int
    step_path: str


class RunArtifactRecordDocument(TypedDict):
    filename: str
    artifact_type: str
    role: str
    byte_count: int


class WorkItemRecordDocument(TypedDict):
    work_item_id: str
    work_item_name: str
    work_item_status: str
    started_at: str
    elapsed_seconds: float | None
    failure: str | None
    step_records: list[StepRecordDocument]
    artifact_records: list[ArtifactRecordDocument]


class ManifestDocument(TypedDict):
    """The run manifest exactly as a run writes it: the JSON an engineer opens first."""

    pipeline_name: str
    run_id: str
    run_status: str
    started_at: str
    finished_at: str
    elapsed_seconds: float
    work_item_records: list[WorkItemRecordDocument]
    run_artifact_records: list[RunArtifactRecordDocument]


def parse_manifest_document(manifest_content: bytes | str) -> ManifestDocument:
    return cast(ManifestDocument, json.loads(manifest_content))
