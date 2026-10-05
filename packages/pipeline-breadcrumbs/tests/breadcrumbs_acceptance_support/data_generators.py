import secrets

from pipeline_breadcrumbs import WorkItem

_RANDOM_SUFFIX_BYTES: int = 4


def create_random_work_item() -> WorkItem:
    """A work item whose identity and name no other test shares, so a scenario never collides with another."""
    random_suffix: str = secrets.token_hex(_RANDOM_SUFFIX_BYTES)
    return WorkItem(id=f"work-item-{random_suffix}", name=f"Document {random_suffix}.pdf")
