import secrets

from pipeline_breadcrumbs import WorkItem

_RANDOM_SUFFIX_BYTES: int = 4
_DISCRIMINATOR_PAGE_LIMIT: int = 10_000


def create_random_work_item() -> WorkItem:
    """A work item whose identity and name no other test shares, so a scenario never collides with another."""
    random_suffix: str = secrets.token_hex(_RANDOM_SUFFIX_BYTES)
    return WorkItem(id=f"work-item-{random_suffix}", name=f"Document {random_suffix}.pdf")


def create_random_pipeline_name() -> str:
    return f"pipeline-{secrets.token_hex(_RANDOM_SUFFIX_BYTES)}"


def create_random_discriminator() -> str:
    return f"page_{secrets.randbelow(_DISCRIMINATOR_PAGE_LIMIT):04d}"


def create_random_outcome() -> str:
    return f"Outcome {secrets.token_hex(_RANDOM_SUFFIX_BYTES)}"


def create_random_failure_message() -> str:
    return f"Failure {secrets.token_hex(_RANDOM_SUFFIX_BYTES)}"


def create_random_skip_reason() -> str:
    return f"Skip reason {secrets.token_hex(_RANDOM_SUFFIX_BYTES)}"


def create_random_progress_message() -> str:
    return f"Progress {secrets.token_hex(_RANDOM_SUFFIX_BYTES)}"


def create_random_log_message() -> str:
    return f"Log message {secrets.token_hex(_RANDOM_SUFFIX_BYTES)}"


def create_random_logger_name() -> str:
    return f"logger_{secrets.token_hex(_RANDOM_SUFFIX_BYTES)}"


def create_random_source_path() -> str:
    return f"source_{secrets.token_hex(_RANDOM_SUFFIX_BYTES)}.py"


def create_random_attribute_name() -> str:
    """A caller attribute name no LogRecord attribute or library attribute shares."""
    return f"caller_attribute_{secrets.token_hex(_RANDOM_SUFFIX_BYTES)}"
