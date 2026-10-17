"""The demo's service locator: the real system, configured to talk to the in-process model service."""

from typing import Final, final, override

import httpx

from pipeline_breadcrumbs_app.document_analysis.configuration_providers.configuration_provider import ConfigurationProvider
from pipeline_breadcrumbs_app.document_analysis.configuration_providers.settings_providers.settings_provider_model_service import (
    MODEL_SERVICE_BASE_URL_VARIABLE_NAME,
)
from pipeline_breadcrumbs_app.document_analysis.configuration_providers.settings_providers.settings_provider_simulated_work import (
    SIMULATED_WORK_SECONDS_VARIABLE_NAME,
)
from pipeline_breadcrumbs_app.document_analysis.service_locators.service_locator_base import ServiceLocatorBase
from pipeline_breadcrumbs_app.model_service_simulator import ModelServiceSimulator

# Never resolved: the simulator answers at the transport, before any name lookup.
DEMO_MODEL_SERVICE_BASE_URL: Final[str] = "http://model-service.demo"
# Non-model processing takes a third of a model call, roughly the proportion in a real pipeline.
_SIMULATED_WORK_SHARE_OF_MODEL_LATENCY: Final[float] = 1 / 3


@final
class ServiceLocatorDemo(ServiceLocatorBase):
    """Swaps exactly what production would supply differently: where the model service is, and the wire to it.

    The configuration provider is the real one, given explicit values instead of environment variables,
    so the demo needs no setup.
    """

    def __init__(self, model_latency_seconds: float) -> None:
        self._model_latency_seconds: float = model_latency_seconds

    @override
    def get_configuration_provider(self) -> ConfigurationProvider:
        return ConfigurationProvider(
            {
                MODEL_SERVICE_BASE_URL_VARIABLE_NAME: DEMO_MODEL_SERVICE_BASE_URL,
                SIMULATED_WORK_SECONDS_VARIABLE_NAME: str(self._model_latency_seconds * _SIMULATED_WORK_SHARE_OF_MODEL_LATENCY),
            }
        )

    @override
    def create_http_transport(self) -> httpx.AsyncBaseTransport:
        return ModelServiceSimulator(self._model_latency_seconds).create_http_transport()
