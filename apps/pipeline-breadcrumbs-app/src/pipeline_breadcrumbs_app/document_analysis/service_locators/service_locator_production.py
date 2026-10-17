from typing import final, override

import httpx

from pipeline_breadcrumbs_app.document_analysis.configuration_providers.configuration_provider import ConfigurationProvider
from pipeline_breadcrumbs_app.document_analysis.service_locators.service_locator_base import ServiceLocatorBase


@final
class ServiceLocatorProduction(ServiceLocatorBase):
    @override
    def get_configuration_provider(self) -> ConfigurationProvider:
        return ConfigurationProvider()

    @override
    def create_http_transport(self) -> httpx.AsyncBaseTransport:
        return httpx.AsyncHTTPTransport()
