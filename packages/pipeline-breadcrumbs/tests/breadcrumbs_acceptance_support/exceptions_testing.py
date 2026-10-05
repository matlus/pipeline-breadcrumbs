from pipeline_breadcrumbs import ContextualDataDict


class DiagnosticTestingError(Exception):
    """An exception shaped like a host's application base exception: a message and named contextual data."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self._contextual_data_by_name: ContextualDataDict = {}

    @property
    def contextual_data_by_name(self) -> ContextualDataDict:
        return dict(self._contextual_data_by_name)

    def add_contextual_data(self, contextual_data_by_name: ContextualDataDict) -> None:
        self._contextual_data_by_name.update(contextual_data_by_name)
