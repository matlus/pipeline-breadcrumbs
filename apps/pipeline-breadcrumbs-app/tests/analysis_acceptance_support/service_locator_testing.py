from collections.abc import Mapping
from typing import Final, final, override

import httpx

from analysis_acceptance_support.mediator_model_service import TestMediatorModelService
from pipeline_breadcrumbs_app.document_analysis.configuration_providers.configuration_provider import ConfigurationProvider
from pipeline_breadcrumbs_app.document_analysis.configuration_providers.settings_providers.settings_provider_model_service import (
    MODEL_SERVICE_BASE_URL_VARIABLE_NAME,
)
from pipeline_breadcrumbs_app.document_analysis.document_analysis_manager import DocumentAnalysisManager
from pipeline_breadcrumbs_app.document_analysis.service_locators.service_locator_base import ServiceLocatorBase

# Never resolved: the Test Mediator answers at the transport.
TEST_MODEL_SERVICE_BASE_URL: Final[str] = "http://model-service.test"


@final
class ServiceLocatorTesting(ServiceLocatorBase):
    # Test-side service locator. The ConfigurationProvider it creates is the real one - never a double -
    # given explicit values so every configuration arrangement is visible in the test, not smuggled in
    # through the process environment.
    #
    # The HTTP transport is the one thing genuinely swapped: it comes from the TestMediatorModelService,
    # so the gateway runs for real and only the wire differs.

    def __init__(
        self,
        test_mediator_model_service: TestMediatorModelService,
        override_by_environment_variable_name: Mapping[str, str] | None = None,
    ) -> None:
        self._test_mediator_model_service: TestMediatorModelService = test_mediator_model_service
        self._override_by_environment_variable_name: dict[str, str] = {
            MODEL_SERVICE_BASE_URL_VARIABLE_NAME: TEST_MODEL_SERVICE_BASE_URL,
            **(override_by_environment_variable_name or {}),
        }

    @override
    def get_configuration_provider(self) -> ConfigurationProvider:
        return ConfigurationProvider(self._override_by_environment_variable_name)

    @override
    def create_http_transport(self) -> httpx.AsyncBaseTransport:
        return self._test_mediator_model_service.create_http_transport()


def create_document_analysis_manager(
    test_mediator_model_service: TestMediatorModelService,
    override_by_environment_variable_name: Mapping[str, str] | None = None,
) -> DocumentAnalysisManager:
    # The single place every test builds the system. The manager takes only a service locator, so
    # everything a test arranges is arranged through that.
    return DocumentAnalysisManager(ServiceLocatorTesting(test_mediator_model_service, override_by_environment_variable_name))
