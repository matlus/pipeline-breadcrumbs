"""The attribute names carried on every log record, and the value types they accept.

Every record the library writes carries named attributes through the standard
`extra` argument of `logging`. Any handler receives them: the human formatter in this
package reads them, and an OpenTelemetry handler (Azure Monitor Application Insights,
for one) turns them into custom dimensions without any code here knowing it exists.

The `pipeline.` prefix is this library's own namespace. No standard defines it. It is
fixed so that one query works across every pipeline built on the library; what differs
between pipelines is the value of `pipeline.name`.
"""

from typing import Final, final

type AttributeValue = str | int | float | bool
type AttributeBag = dict[str, AttributeValue]


@final
class AttributeKey:
    """Names of the attributes. Never instantiated; a namespace of constants."""

    PIPELINE_NAME: Final[str] = "pipeline.name"
    RUN_ID: Final[str] = "pipeline.run.id"
    WORK_ITEM_ID: Final[str] = "pipeline.work_item.id"
    WORK_ITEM_NAME: Final[str] = "pipeline.work_item.name"

    # Present on boundary records only.
    EVENT: Final[str] = "pipeline.event"
    STATUS: Final[str] = "pipeline.status"
    ELAPSED_SECONDS: Final[str] = "pipeline.elapsed_seconds"
    OUTCOME: Final[str] = "pipeline.outcome"

    STEP_NUMBER: Final[str] = "pipeline.step.number"
    STEP_NAME: Final[str] = "pipeline.step.name"
    STEP_KEY: Final[str] = "pipeline.step.key"

    ARTIFACT_KIND: Final[str] = "pipeline.artifact.kind"
    ARTIFACT_FILENAME: Final[str] = "pipeline.artifact.filename"
    ARTIFACT_BYTES: Final[str] = "pipeline.artifact.bytes"

    FAILURE_TYPE: Final[str] = "pipeline.failure.type"
    FAILURE_MESSAGE: Final[str] = "pipeline.failure.message"

    DETAIL_PREFIX: Final[str] = "pipeline.detail."


@final
class EventKind:
    """Values of `pipeline.event`: which kind of boundary a record marks."""

    RUN: Final[str] = "run"
    WORK_ITEM: Final[str] = "work_item"
    STEP: Final[str] = "step"


def detail_key(name: str) -> str:
    """Namespace a caller-supplied field so it can never collide with a `LogRecord` attribute."""
    return f"{AttributeKey.DETAIL_PREFIX}{name}"
