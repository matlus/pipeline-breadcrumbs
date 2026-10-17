from abc import ABC, abstractmethod

import httpx

from pipeline_breadcrumbs_app.document_analysis.configuration_providers.configuration_provider import ConfigurationProvider


class ServiceLocatorBase(ABC):
    """Creates the system's infrastructure components. Used only by `DocumentAnalysisManager`.

    It creates only what a host or a test must swap; everything else is created directly by its owner
    (the manager creates the gateway and the processors). The HTTP transport is the classic member of
    that swap set: production supplies the real network transport, a test supplies its Test Mediator's
    transport, so the gateway runs for real everywhere and only the wire differs.
    """

    @abstractmethod
    def get_configuration_provider(self) -> ConfigurationProvider: ...

    @abstractmethod
    def create_http_transport(self) -> httpx.AsyncBaseTransport: ...
